import hashlib
import json
import os
import sqlite3
from datetime import timedelta
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import pytest
from fastapi.testclient import TestClient
from google.transit import gtfs_realtime_pb2 as g
from app import pilot_store as store,feeds,ground_truth as truth
from app.main import app,sim

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
 monkeypatch.setattr(store,'DB_PATH',tmp_path/'pilot.db');monkeypatch.setenv('RUSHLESS_DATA_MODE','simulation');monkeypatch.setenv('RUSHLESS_SOURCE_ID','fixture');monkeypatch.setenv('GTFS_DB_PATH',str(tmp_path/'fixture-gtfs.db'))
 feeds.cached_trip.cache_clear();feeds.ROUTE_CACHE.clear();truth.submission_limits.clear();sim.reset('normal')
 yield
 feeds.cached_trip.cache_clear();feeds.ROUTE_CACHE.clear();sim.reset('normal')
def fixture(tmp_path):
 db,file=feeds.fixture(tmp_path);return db,file.read_bytes()
def ingest(raw,path,synthetic=True):return feeds.ingest(raw,sid='fixture',provenance='Synthetic local engineering test',license_name='CC0 test fixture',synthetic=synthetic,path=path)
def real_registry(path):
 # Unit test stand-in only; not evidence of a genuine provider or genuine labels.
 with sqlite3.connect(path) as db:db.execute('UPDATE rushless_registry_metadata SET synthetic=0')
 feeds.cached_trip.cache_clear()

def test_gtfs_realtime_parsing_and_replay_serving(tmp_path,monkeypatch):
 db,raw=fixture(tmp_path);header,records=feeds.parse_feed(raw)
 assert [r['kind'] for r in records]==['vehicle_position','trip_update']
 assert ingest(raw,db)['accepted']==2
 assert ingest(raw,db)['duplicates']==2
 monkeypatch.setenv('RUSHLESS_DATA_MODE','replay')
 c=TestClient(app);vs=c.get('/api/vehicles').json();assert any(v['id']=='FIXTURE-BUS' for v in vs)
 assert c.get('/api/data-health').json()['live_connected'] is False
 result=c.get('/api/journeys?origin=20598&destination=marathahalli').json()['journeys']
 assert result and result[0]['metadata']['source']=='replay_synthetic'
 assert result[0]['crowding']=='Unknown' and result[0]['utilization'] is None
 assert c.get('/api/vehicles/FIXTURE-BUS/forecast').status_code==200

@pytest.mark.parametrize('change,expected',[('unknown','unmatched'),('direction','rejected'),('position','rejected'),('future','rejected'),('missing_vehicle','rejected'),('stale','stale')])
def test_feed_validation(tmp_path,change,expected):
 db,raw=fixture(tmp_path);_,records=feeds.parse_feed(raw);record=records[0];clock=store.now()
 if change=='unknown':record['trip_id']='bad'
 if change=='direction':record['direction']=1
 if change=='position':record['latitude']=90
 if change=='future':record['observed_timestamp']=int(clock.timestamp())+300
 if change=='missing_vehicle':record['vehicle_id']=None
 if change=='stale':record['observed_timestamp']=int(clock.timestamp())-300
 normalized=feeds.normalize(record,'fixture',clock,db)
 assert normalized['status']==expected

def test_out_of_order_jump_and_synthetic_source_boundaries(tmp_path):
 db,raw=fixture(tmp_path);_,records=feeds.parse_feed(raw);first=feeds.normalize(records[0],'fixture',store.now(),db)
 assert feeds.normalize(records[0],'fixture',store.now(),db,first)['status']=='rejected'
 later={**records[0],'observed_timestamp':records[0]['observed_timestamp']+1,'feed_timestamp':records[0]['feed_timestamp']+1,'latitude':12.98,'longitude':77.75}
 assert feeds.normalize(later,'fixture',store.now()+timedelta(seconds=2),db,first)['status']=='rejected'
 assert ingest(raw,db,synthetic=False)['rejected']==2
 with pytest.raises(ValueError):feeds.ingest(raw,sid='live',provenance='x',license_name='y',source_mode='authorized',synthetic=True,path=db)

def test_bad_protobuf_and_safe_url(tmp_path,monkeypatch):
 with pytest.raises(ValueError):ingest(b'not a protobuf',tmp_path/'none')
 with store.connect() as db:assert db.execute("SELECT status FROM raw_feeds").fetchone()[0]=='rejected'
 for url in ['http://provider.example/feed','https://127.0.0.1/feed','https://evil.example/feed','https://user:secret@provider.example/feed']:
  with pytest.raises(ValueError):feeds.safe_url(url,{'provider.example'})
 monkeypatch.setattr(feeds.socket,'getaddrinfo',lambda *args,**kwargs:[(0,0,0,'',('127.0.0.1',443))])
 with pytest.raises(ValueError):feeds.safe_url('https://provider.example/feed',{'provider.example'})
 with pytest.raises(ValueError):feeds.fetch_configured()

def test_profile_persistence_isolation_reset_and_csrf():
 a,b=TestClient(app),TestClient(app)
 first=a.get('/api/profile');assert 'HttpOnly' in first.headers['set-cookie'] and 'SameSite=strict' in first.headers['set-cookie']
 a.patch('/api/profile/preferences',json={'preference':'fastest','alerts_enabled':False})
 item=a.post('/api/profile/saved-journeys',json={'origin':'silk','destination':'marathahalli','name':'College'}).json()['saved'][0]
 assert a.get('/api/profile').json()['preference']=='fastest'
 assert b.get('/api/profile').json()['saved']==[]
 assert b.patch('/api/profile/saved-journeys/'+item['id'],json={'name':'hijack'}).status_code==404
 a.patch('/api/profile/saved-journeys/'+item['id'],json={'name':'Morning college'})
 assert a.get('/api/profile').json()['saved'][0]['name']=='Morning college'
 a.post('/api/profile/recent',json={'origin':'silk','destination':'marathahalli'})
 assert a.get('/api/profile').json()['last_context']['origin']=='silk'
 assert a.post('/api/profile/recent',json={'origin':'silk','destination':'silk'}).status_code==422
 a.delete('/api/profile/recent');assert a.get('/api/profile').json()['recent']==[]
 a.delete('/api/profile/saved-journeys/'+item['id']);assert a.get('/api/profile').json()['saved']==[]
 a.delete('/api/profile');assert a.get('/api/profile').json()['preference']=='comfortable'
 assert a.patch('/api/profile/preferences',json={'preference':'fastest'},headers={'Origin':'https://attacker.example'}).status_code==403
 token='a'*64;b.cookies.set('rushless_commuter',token);response=b.get('/api/profile');assert token not in response.headers['set-cookie']

def body(route='demo-2',trip=None):
 from app.main import ROUTES
 r=next((r for r in ROUTES if r['id']==route),None)
 return dict(route_id=route,stop_id='silk',direction=r['direction'] if r else '0',service_date=store.now().astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata')).strftime('%Y%m%d'),trip_id=trip,event_at=(store.now()-timedelta(minutes=1)).isoformat(),method='volunteer_manual')
def test_pilot_submission_privacy_and_verification_gate(tmp_path):
 c=TestClient(app);payload=body(trip='demo-2-trip-0')
 response=c.post('/api/observations/arrivals',json=payload);assert response.status_code==201
 result=response.json();assert result['source_type']=='simulation' and result['status']=='matched'
 assert c.post('/api/observations/arrivals',json=payload).status_code==409
 with pytest.raises(ValueError):truth.verify(result['id'],status='verified',evidence='test',reviewer='operator')
 assert c.post('/api/observations/occupancy',json={**body(), 'category':'High'}).status_code==201
 assert c.post('/api/observations/occupancy',json={**body(),'passenger_count':40,'capacity':60}).status_code==422
 assert c.post('/api/observations/arrivals',json={**body(),'event_at':(store.now()+timedelta(hours=1)).isoformat()}).status_code==422
 assert c.get('/api/predictions/evaluation').json()['verified_events']==0
 assert c.get('/api/predictions/calibration-status').json()['available'] is False

def test_genuine_review_is_separate_from_matching(tmp_path):
 db,raw=fixture(tmp_path);real_registry(db)
 c=TestClient(app);payload=body('gtfs:fixture-route:0','fixture-trip')
 response=c.post('/api/observations/arrivals',json=payload);assert response.status_code==201
 result=response.json();assert result['source_type']=='real_observed' and result['status']=='matched'
 assert truth.matched_pairs()==[]
 truth.verify(result['id'],status='verified',evidence='Mock operator evidence for unit test',reviewer='unit-test')
 assert c.get('/api/data-health').json()['verified_labels']==1
 assert truth.evaluate_real()['verified_events']==0  # no forecast existed before arrival

def test_forward_forecast_matching_and_small_sample_calibration(tmp_path):
 event=store.now()-timedelta(minutes=1);created=event-timedelta(minutes=10)
 label=dict(kind='arrival',transport_source_id='test-source',trip_id='trip',service_date='20261105',stop_id='silk',route_id='gtfs:test:0',event_at=event.isoformat(),matched=True)
 with store.connect() as db:
  db.execute('INSERT INTO pilot_observations VALUES (?,?,?,?,?,?,?,?,?,?)',('label','fingerprint','arrival',store.stamp(),event.isoformat(),'real_observed','verified','{}',json.dumps(label),'[]'))
  for ident,at in [('before',created),('after',event+timedelta(minutes=2))]:
   db.execute('INSERT INTO forecasts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(ident,at.isoformat(),'test-source','real_observed','trip','20261105','silk','vehicle_progress',truth.FORECAST_VERSION,(event+timedelta(minutes=2)).isoformat(),'Unknown','{}'))
 pairs=truth.matched_pairs();assert len(pairs)==1 and pairs[0]['error_minutes']==2
 report=truth.evaluate_real();assert report['verified_events']==1 and report['reliable'] is False
 assert truth.calibration_status()['available'] is False
 assert truth.conformal_radius([1,2,3,4],.9)==4

def test_sufficient_verified_calibration_and_activation(monkeypatch):
 # All evidence is mocked in an isolated DB; never a claim about a connected provider.
 pairs=[];base=store.now()-timedelta(days=40)
 for trip in range(30):
  for stop in range(5):
   actual=base+timedelta(days=trip,minutes=stop)
   for method in ['scheduled_baseline','vehicle_progress']:
    pairs.append(dict(key=f'{trip}-{stop}',kind='arrival',group=f'trip-{trip}',source_id='test-source',route_id='gtfs:test:0',method=method,created_at=(actual-timedelta(minutes=10)).isoformat(),event_at=actual.isoformat(),error_minutes=2 if method=='scheduled_baseline' else 1))
 monkeypatch.setattr(truth,'matched_pairs',lambda:pairs)
 report=truth.evaluate_real();assert report['reliable'] and report['split']['test']['rows']==30
 candidates=truth.calibration_status()['candidates'];assert candidates and not truth.calibration_status()['available']
 truth.activate_calibration(candidates[0]['id']);assert truth.calibration_status()['available']
 monkeypatch.setenv('RUSHLESS_SOURCE_ID','test-source')
 chosen=candidates[0];bounds=truth.calibrated_bounds(chosen['method'],'gtfs:test:0',600,{'kind':'heuristic'})
 assert bounds['calibrated'] and bounds['kind']=='empirical'
 assert truth.calibrated_bounds(chosen['method'],'other-route',600,{'kind':'heuristic'})['kind']=='heuristic'

def test_mock_authorized_http_fetch_polling_and_prediction_ledger(tmp_path,monkeypatch):
 # Transport is mocked; this test never contacts a provider.
 import httpx
 from contextlib import contextmanager
 db,raw=fixture(tmp_path);real_registry(db)
 for key,value in {'TRANSIT_FEED_AUTHORIZED':'true','TRANSIT_FEED_URL':'https://provider.example/feed','TRANSIT_FEED_ALLOWED_HOSTS':'provider.example','TRANSIT_FEED_PROVENANCE':'mock provider test','TRANSIT_FEED_LICENSE':'mock test license','TRANSIT_FEED_TOKEN':'PRIVATE_TEST_TOKEN','RUSHLESS_DATA_MODE':'authorized'}.items():monkeypatch.setenv(key,value)
 monkeypatch.setattr(feeds.socket,'getaddrinfo',lambda *args,**kwargs:[(0,0,0,'',('8.8.8.8',443))])
 class MockClient:
  def __init__(self,**kwargs):assert kwargs['follow_redirects'] is False
  def __enter__(self):return self
  def __exit__(self,*args):pass
  @contextmanager
  def stream(self,method,url,headers):
   assert headers['Authorization']=='Bearer PRIVATE_TEST_TOKEN'
   yield httpx.Response(200,content=raw,request=httpx.Request('GET',url))
 monkeypatch.setattr(feeds.httpx,'Client',MockClient)
 assert feeds.fetch_configured()['accepted']==2
 assert feeds.health()['live_connected'] is True
 with pytest.raises(ValueError,match='polling'):feeds.fetch_configured()
 elapsed,clock,vs=feeds.external_snapshot();v=next(v for v in vs if v['id']=='FIXTURE-BUS')
 point=feeds.external_prediction(v,'marathahalli',elapsed,clock)
 assert point['metadata']['source']=='real_observed' and point['utilization'] is None
 with store.connect() as conn:assert conn.execute('SELECT COUNT(*) FROM forecasts').fetchone()[0]==2
 assert 'PRIVATE_TEST_TOKEN' not in json.dumps(feeds.health())

def test_profile_retention_and_alert_preferences():
 a=TestClient(app);a.get('/api/profile');a.patch('/api/profile/preferences',json={'preference':'fastest'})
 with store.connect() as db:db.execute('UPDATE commuter_profiles SET last_seen=?',((store.now()-timedelta(days=31)).isoformat(),))
 assert a.get('/api/profile').json()['preference']=='comfortable'
 key=a.post('/api/watches',json={'trip_id':'demo-2-trip-0','origin':'silk','destination':'marathahalli','alerts_enabled':False}).json()['id']
 a.post('/api/demo/scenario',json={'scenario':'traffic'})
 state=a.get('/api/watches/'+key+'?alerts_enabled=false').json()
 assert state['alerts']==[] and state['alternative'] is None

def test_history_training_requires_verified_export(tmp_path):
 from app.history import make_demo_csv,import_csv,evaluate
 import csv
 file=tmp_path/'unverified.csv';make_demo_csv(file)
 with file.open() as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
 for row in rows:row['source_type']='real_observed'
 with file.open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
 db=tmp_path/'history.db';key=import_csv(file,source='unverified unit fixture',license_name='CC0',collected_on='2026-11-05',mode='real_observed',db_path=db)
 with pytest.raises(ValueError,match='genuine'):evaluate(key,db_path=db,train_model=True)

def test_verified_history_export_requires_pre_arrival_features(tmp_path):
 with pytest.raises(ValueError,match='No verified'):truth.export_verified_history(tmp_path/'verified.csv')
 assert not (tmp_path/'verified.csv').exists()

def test_timestamp_overflow_is_rejected_safely(tmp_path):
 db,raw=fixture(tmp_path);message=g.FeedMessage();message.ParseFromString(raw);message.header.timestamp=2**64-1
 with pytest.raises(ValueError,match='timestamp'):feeds.parse_feed(message.SerializeToString())
 _,records=feeds.parse_feed(raw);record={**records[0],'observed_timestamp':2**64-1}
 assert feeds.normalize(record,'fixture',store.now(),db)['status']=='rejected'

def test_ambiguous_start_time_is_not_guessed(tmp_path):
 db,raw=fixture(tmp_path);_,records=feeds.parse_feed(raw)
 record={**records[0],'start_time':'49:00:00'}
 normalized=feeds.normalize(record,'fixture',store.now(),db)
 assert normalized['status']=='rejected' and any('frequency' in f for f in normalized['flags'])
