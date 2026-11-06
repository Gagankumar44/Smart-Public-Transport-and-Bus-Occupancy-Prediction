"""Local protobuf fixtures only: no provider access or claims of real observations."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from datetime import datetime,timedelta,timezone
import pytest
from fastapi.testclient import TestClient
from google.transit import gtfs_realtime_pb2 as g
from app import feeds,main,intelligence,pilot_store as store,disruptions

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
 main.sim.reset('normal');intelligence.watches.clear()
 monkeypatch.setenv('RUSHLESS_SOURCE_ID','local-disruption-test')
 monkeypatch.setenv('GTFS_DB_PATH',str(tmp_path/'fixture-gtfs.db'))
 feeds.cached_trip.cache_clear();feeds.PREVIEW_CACHE.clear()
 yield
 main.sim.reset('normal');intelligence.watches.clear();feeds.cached_trip.cache_clear();feeds.PREVIEW_CACHE.clear()

def watch(client):
 return client.post('/api/watches',json=dict(trip_id='demo-2-trip-0',origin=main.STOPS[0]['id'],destination=main.STOPS[-1]['id'])).json()['id']

def test_onboard_survives_boarding_stop_and_updates_destination_delay():
 c=TestClient(main.app);key=watch(c);path='/api/watches/'+key
 assert c.patch(path+'/progress',json=dict(current_stop=main.STOPS[0]['id'])).json()['phase']=='onboard'
 main.sim.started-=700
 state=c.get(path).json()
 assert state['available'] and state['current']['wait_minutes']==0
 assert state['current']['total_minutes']>0
 assert not any(a['kind']=='unavailable' for a in state['alerts'])
 main.sim.corrections['SIM-20']=360
 delayed=c.get(path).json()
 assert datetime.fromisoformat(delayed['current']['arrival_at'])>datetime.fromisoformat(state['current']['arrival_at'])+timedelta(minutes=5)
 assert any(a['kind']=='delay' for a in delayed['alerts'])

def test_gradually_accumulated_delay_triggers_alert():
 c=TestClient(main.app);key=watch(c);path='/api/watches/'+key
 for correction in [60,120,180]:
  main.sim.corrections['SIM-20']=correction
  state=c.get(path).json()
 assert any(a['kind']=='delay' for a in state['alerts'])

def test_schedule_only_arrivals_do_not_emit_demo_or_bunching_notices(monkeypatch):
 c=TestClient(main.app)
 items=c.get('/api/stops/'+main.STOPS[0]['id']+'/arrivals').json()
 for p in items:p['metadata']['source']='schedule'
 monkeypatch.setattr(main,'arrivals',lambda sid:items)
 monkeypatch.setenv('RUSHLESS_DATA_MODE','schedule')
 assert intelligence.close_arrivals(main.STOPS[0]['id'])==[]

@pytest.mark.parametrize('incident',['breakdown','diversion'])
def test_personal_disruption_reroutes_from_confirmed_stop_and_accepts(incident):
 c=TestClient(main.app);key=watch(c);other=watch(c);path='/api/watches/'+key
 at=main.STOPS[2]['id'];main.sim.started-=700
 state=c.patch(path+'/progress',json=dict(current_stop=at,incident=incident)).json()
 assert state['phase']=='onboard' and not state['available']
 assert state['disruptions'][0]['kind']=='commuter_report'
 assert state['alternative']['origin']['id']==at and state['alternative']['id']!='demo-2-trip-0'
 assert c.get('/api/watches/'+other).json()['incident']=='none'
 accepted=c.post(path+'/decision',json={'action':'accept'}).json()
 assert accepted['phase']=='waiting' and accepted['incident']=='none'
 assert accepted['current']['origin']['id']==at
 assert accepted['current']['wait_minutes']>0

def test_progress_validation_and_arrival_stops_alternatives():
 c=TestClient(main.app);key=watch(c);path='/api/watches/'+key+'/progress'
 assert c.patch(path,json={'current_stop':'unknown'}).status_code==422
 assert c.patch(path,json={'current_stop':main.STOPS[2]['id']}).status_code==200
 assert c.patch(path,json={'current_stop':main.STOPS[0]['id']}).status_code==422
 assert c.patch(path,json={'current_stop':main.STOPS[-1]['id']}).status_code==422
 state=c.patch(path,json={'current_stop':main.STOPS[-1]['id'],'phase':'arrived'}).json()
 assert state['phase']=='arrived' and state['alternative'] is None
 assert not any(a['kind']=='unavailable' for a in state['alerts'])
 assert c.patch(path,json={'current_stop':main.STOPS[-1]['id'],'phase':'arrived'}).status_code==409

def setup_feed(tmp_path,monkeypatch):
 db,file=feeds.fixture(tmp_path);message=g.FeedMessage();message.ParseFromString(file.read_bytes())
 monkeypatch.setenv('RUSHLESS_DATA_MODE','replay')
 return db,message

def ingest(message,db):
 return feeds.ingest(message.SerializeToString(),sid='local-disruption-test',provenance='Synthetic local test',license_name='CC0 fixture',synthetic=True,path=db)

def test_cancelled_trip_without_vehicle_or_timestamp_is_removed_and_can_recover(tmp_path,monkeypatch):
 db,message=setup_feed(tmp_path,monkeypatch)
 message.ClearField('entity');entity=message.entity.add();entity.id='cancelled'
 u=entity.trip_update;u.trip.trip_id='fixture-trip';u.trip.start_date=store.now().astimezone(main.TZ).strftime('%Y%m%d');u.trip.schedule_relationship=g.TripDescriptor.CANCELED
 assert ingest(message,db)['cancelled']==1
 _,clock,vs=feeds.external_snapshot();v=next(v for v in vs if v['trip_id']=='fixture-trip')
 assert feeds.external_prediction(v,main.STOPS[-1]['id'],0,clock) is None
 # Stale cancellation cannot indefinitely override the published timetable.
 fallback=feeds.external_prediction(v,main.STOPS[-1]['id'],0,clock+timedelta(seconds=121))
 assert fallback and fallback['metadata']['source']=='schedule'
 # A new FULL_DATASET without that entity withdraws the cancellation.
 message.header.timestamp+=1;message.ClearField('entity');ingest(message,db)
 assert feeds.current_records()[1]==[]
 assert feeds.external_snapshot()[1].timestamp()==message.header.timestamp
 with pytest.raises(ValueError,match='Out-of-order'):
  message.header.timestamp-=2;ingest(message,db)

def test_alert_scope_direction_expiry_and_full_snapshot_withdrawal(tmp_path,monkeypatch):
 db,message=setup_feed(tmp_path,monkeypatch)
 a=message.entity.add();a.id='detour';alert=a.alert;alert.effect=g.Alert.DETOUR;alert.cause=g.Alert.TECHNICAL_PROBLEM
 alert.header_text.translation.add(text='Fixture diversion')
 selector=alert.informed_entity.add();selector.route_id='fixture-route';selector.direction_id=0;selector.stop_id=main.STOPS[3]['id']
 period=alert.active_period.add();period.start=message.header.timestamp-1;period.end=message.header.timestamp+60
 assert ingest(message,db)['informational']==1
 _,clock,vs=feeds.external_snapshot();v=next(v for v in vs if v['id']=='FIXTURE-BUS')
 found=disruptions.for_journey(v,main.STOPS[2]['id'],main.STOPS[-1]['id'],clock)
 assert found and found[0]['blocking'] and found[0]['effect']=='detour'
 assert not disruptions.active_alerts(clock+timedelta(seconds=60))
 info=feeds.trip_info('fixture-trip');date=v['service_date'];stops={main.STOPS[3]['id']}
 assert not disruptions.selector_matches({'route_id':'another','stop_id':main.STOPS[3]['id']},info,date,stops)
 assert not disruptions.selector_matches({'route_id':'fixture-route','direction_id':1},info,date,stops)
 # Route-wide detours are not represented as a confidently usable old path.
 c=TestClient(main.app)
 assert c.get('/api/journeys',params={'origin':main.STOPS[2]['id'],'destination':main.STOPS[-1]['id']}).json()['journeys']==[]
 message.ClearField('entity');message.header.timestamp+=1;ingest(message,db)
 assert disruptions.active_alerts(clock+timedelta(seconds=1))==[]

def test_no_data_keeps_schedule_but_skipped_stop_is_not_boardable(tmp_path,monkeypatch):
 db,message=setup_feed(tmp_path,monkeypatch)
 u=message.entity[1].trip_update;u.ClearField('stop_time_update');u.delay=600
 update=u.stop_time_update.add();update.stop_id=main.STOPS[2]['id'];update.schedule_relationship=g.TripUpdate.StopTimeUpdate.NO_DATA
 ingest(message,db);_,clock,vs=feeds.external_snapshot();v=next(v for v in vs if v['id']=='FIXTURE-BUS')
 point=feeds.external_prediction(v,main.STOPS[3]['id'],0,clock)
 assert point and point['metadata']['source']=='schedule' and point['delay_minutes']==0
 update.schedule_relationship=g.TripUpdate.StopTimeUpdate.SKIPPED
 message.header.timestamp+=1;u.timestamp+=1;ingest(message,db)
 _,clock,vs=feeds.external_snapshot();v=next(v for v in vs if v['trip_id']=='fixture-trip')
 assert feeds.external_prediction(v,main.STOPS[2]['id'],0,clock) is None
 assert feeds.external_prediction(v,main.STOPS[3]['id'],0,clock) is not None

def test_stop_update_identifier_conflicts_are_rejected(tmp_path,monkeypatch):
 db,message=setup_feed(tmp_path,monkeypatch)
 u=message.entity[1].trip_update.stop_time_update[0];u.stop_sequence=1
 result=ingest(message,db)
 assert result['rejected']==1

def test_replay_disruptions_cannot_leak_into_schedule_mode(tmp_path,monkeypatch):
 db,message=setup_feed(tmp_path,monkeypatch);ingest(message,db)
 assert feeds.current_records()[1]
 monkeypatch.setenv('RUSHLESS_DATA_MODE','schedule')
 assert feeds.current_records()==(None,[])

def test_refreshed_full_feed_can_retain_unchanged_position(tmp_path,monkeypatch):
 db,message=setup_feed(tmp_path,monkeypatch);assert ingest(message,db)['accepted']==2
 message.header.timestamp+=1
 assert ingest(message,db)['accepted']==2
 assert any(r['kind']=='vehicle_position' for r in feeds.current_records()[1])

def test_departure_only_delay_propagates_to_later_stops(tmp_path,monkeypatch):
 db,message=setup_feed(tmp_path,monkeypatch)
 u=message.entity[1].trip_update;u.ClearField('stop_time_update')
 update=u.stop_time_update.add();update.stop_sequence=3;update.departure.delay=300
 assert ingest(message,db)['accepted']==2
 _,clock,vs=feeds.external_snapshot();v=next(v for v in vs if v['id']=='FIXTURE-BUS')
 point=feeds.external_prediction(v,main.STOPS[4]['id'],0,clock)
 assert point['metadata']['method']=='provider_delay' and point['delay_minutes']==5

def test_cancelled_watched_trip_recommends_other_fixture_departure(tmp_path,monkeypatch):
 import sqlite3
 db,message=setup_feed(tmp_path,monkeypatch)
 with sqlite3.connect(db) as conn:
  conn.execute("INSERT INTO trips SELECT 'alternate-trip',route_id,service_id,direction_id FROM trips WHERE trip_id='fixture-trip'")
  conn.execute("INSERT INTO stop_times SELECT 'alternate-trip',stop_id,stop_sequence,arrival_time FROM stop_times WHERE trip_id='fixture-trip'")
 ingest(message,db);c=TestClient(main.app)
 key=c.post('/api/watches',json={'trip_id':'fixture-trip','origin':main.STOPS[2]['id'],'destination':main.STOPS[-1]['id']}).json()['id']
 update=message.entity[1].trip_update;update.trip.schedule_relationship=g.TripDescriptor.CANCELED;update.timestamp+=1;message.header.timestamp+=1
 ingest(message,db)
 state=c.get('/api/watches/'+key).json()
 assert not state['available'] and any(d['kind']=='cancelled' for d in state['disruptions'])
 assert state['alternative']['id']=='alternate-trip'
 assert state['alternative']['metadata']['source']=='schedule'
