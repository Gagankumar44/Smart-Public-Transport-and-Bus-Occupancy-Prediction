import csv
import json
import sqlite3
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import pytest
from fastapi.testclient import TestClient
from app.main import app,sim
from app.predictive import select_eta,uncertainty
from app.history import import_csv,make_demo_csv,evaluate,connect,split_trips,validate_artifact,FEATURES

client=TestClient(app)
@pytest.fixture(autouse=True)
def reset():
 sim.reset('normal');yield;sim.reset('normal')
def test_method_priority_and_stale_fallback():
 assert select_eta(mode='simulation',scheduled_remaining=400,progress_remaining=300,observation_age=0)==(300,'simulation_progress','simulation')
 assert select_eta(mode='simulation',scheduled_remaining=400,progress_remaining=300,observation_age=600,history_remaining=900)==(400,'scheduled_baseline','schedule')
 assert select_eta(mode='real_observed',scheduled_remaining=400,progress_remaining=300,observation_age=0,history_remaining=500)[1]=='history_adjusted_progress'
 assert select_eta(mode='real_observed',scheduled_remaining=400,observation_age=600,history_remaining=500)[0]==500

def test_forecast_matches_journey_and_propagates_uncertainty():
 journey=client.get('/api/journeys?origin=silk&destination=marathahalli').json()['journeys'][0]
 points=client.get(f'/api/vehicles/{journey["vehicle_id"]}/forecast').json()
 assert points[0]['stop_id']=='silk' and points[-1]['stop_id']=='marathahalli'
 assert points[0]['crowding']==journey['crowding']
 assert points[-1]['uncertainty']['upper_minutes']>points[0]['uncertainty']['upper_minutes']
 assert all(0<=p['utilization']<=1 for p in points)
 assert points[0]['metadata']['uncertainty']['calibrated'] is False
 assert len({p['utilization'] for p in points})>1
 assert client.get('/api/vehicles/bad/forecast').status_code==404

def test_demand_profiles_fresh_observation_and_scheduled_fallback():
 normal=client.get('/api/vehicles/SIM-20/forecast').json()
 client.post('/api/demo/scenario',json={'scenario':'normal','demand_profile':'low'})
 low=client.get('/api/vehicles/SIM-20/forecast').json()
 assert low[0]['utilization']<normal[0]['utilization']
 before=low[0]['minutes']
 v=client.post('/api/demo/observation',json={'vehicle_id':'SIM-20','advance_seconds':60}).json()
 after=client.get('/api/vehicles/SIM-20/forecast').json()[0]['minutes']
 assert before-after>=.9 and v['progress']<0
 client.post('/api/demo/scenario',json={'scenario':'traffic'})
 client.post('/api/demo/scenario',json={'scenario':'missing'})
 fallback=client.get('/api/vehicles/SIM-20/forecast').json()[0]
 assert fallback['method']=='scheduled_baseline' and fallback['crowding']=='Unknown'
 assert fallback['metadata']['confidence']=='Low'

def dataset(tmp_path,mode='simulation'):
 path=tmp_path/'observations.csv';make_demo_csv(path);db=tmp_path/'history.db'
 identity=import_csv(path,source='unit test fixture',license_name='CC0',collected_on='2026-11-05',mode=mode,db_path=db)
 return identity,db,path
def test_import_preserves_raw_features_and_provenance(tmp_path):
 identity,db,path=dataset(tmp_path)
 with connect(db) as conn:
  row=conn.execute('SELECT * FROM datasets').fetchone()
  assert row['raw']==path.read_bytes() and row['status']=='ready'
  assert conn.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==72
  assert conn.execute('SELECT COUNT(*) FROM features').fetchone()[0]==72
 with pytest.raises(ValueError,match='already imported'):import_csv(path,source='unit test fixture',license_name='CC0',collected_on='2026-11-05',mode='simulation',db_path=db)

@pytest.mark.parametrize('field,value',[('observed_at','2026-11-05T08:00:00'),('passenger_count','999'),('latitude','500'),('route_id','bad'),('stops_remaining','99'),('stop_id',''),('recent_segment_seconds','nan')])
def test_invalid_history_is_rejected_atomically(tmp_path,field,value):
 path=tmp_path/'bad.csv';make_demo_csv(path)
 with path.open() as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
 rows[0][field]=value
 if field=='latitude' and field not in fields:fields.append(field)
 with path.open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
 db=tmp_path/'bad.db'
 with pytest.raises(ValueError):import_csv(path,source='test',license_name='CC0',collected_on='2026-11-05',mode='simulation',db_path=db)
 with connect(db) as conn:
  assert conn.execute('SELECT status FROM datasets').fetchone()[0]=='rejected'
  assert conn.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==0

def test_chronological_split_metrics_and_training_gate(tmp_path):
 identity,db,_=dataset(tmp_path)
 with connect(db) as conn:rows=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM observations ORDER BY row_number')]
 train,cal,test=split_trips(rows)
 assert not {r['group'] for r in train}&{r['group'] for r in test}
 assert max(r['actual_arrival_at'] for r in train)<min(r['observed_at'] for r in cal)
 report=evaluate(identity,db_path=db)
 assert report['source_type']=='simulation' and report['ml_enabled'] is False
 assert report['methods']['schedule']['metrics']['mae_minutes']==2.667
 assert report['methods']['progress']['metrics']['mae_minutes']==1.667
 assert report['split']['test']['trips']==3
 assert report['occupancy']['forecast']['sample_count']==18
 with pytest.raises(ValueError,match='genuine'):evaluate(identity,db_path=db,train_model=True)

def test_model_compatibility_and_heuristic_bounds():
 artifact=dict(feature_schema=FEATURES,version='eta-ridge-v1',weights=[0]*(len(FEATURES)+1),source_type='real_observed')
 assert validate_artifact(artifact)==artifact
 with pytest.raises(ValueError):validate_artifact({**artifact,'feature_schema':['bad']})
 with pytest.raises(ValueError):validate_artifact({**artifact,'source_type':'simulation'})
 assert uncertainty(600,8,600,'traffic')['upper_minutes']>uncertainty(600,1,0,'normal')['upper_minutes']

def test_gtfs_schedule_calendar_after_midnight(tmp_path):
 from app.schedule import scheduled_arrival
 path=tmp_path/'gtfs.db'
 with sqlite3.connect(path) as db:
  db.executescript("CREATE TABLE trips(trip_id TEXT,service_id TEXT);INSERT INTO trips VALUES ('trip','svc');CREATE TABLE stop_times(trip_id TEXT,stop_id TEXT,stop_sequence TEXT,arrival_time TEXT);INSERT INTO stop_times VALUES ('trip','stop','1','25:10:00');CREATE TABLE calendar_dates(service_id TEXT,date TEXT,exception_type TEXT);INSERT INTO calendar_dates VALUES ('svc','20261105','1');INSERT INTO calendar_dates VALUES ('svc','20261106','2');")
 result=scheduled_arrival(path,'trip','stop','2026-11-05')
 assert result.isoformat()=='2026-11-06T01:10:00+05:30'
 with pytest.raises(ValueError,match='not active'):scheduled_arrival(path,'trip','stop','2026-11-06')

def test_candidate_training_artifact_pipeline_with_mock_observed_labels(tmp_path,monkeypatch):
 from app import history
 monkeypatch.setattr(history,'verified_dataset',lambda _: True)
 # Isolated fixture deliberately exercises the observed-label gate; never real-world evidence.
 path=tmp_path/'mock.csv';make_demo_csv(path)
 with path.open() as f:reader=csv.DictReader(f);fields=reader.fieldnames;original=list(reader)
 rows=[]
 for row in original:
  row['source_type']='real_observed';rows.append(row)
  later={**row,'observed_at':(datetime.fromisoformat(row['observed_at'])+timedelta(seconds=20)).isoformat()};rows.append(later)
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 db=tmp_path/'mock.db';key=import_csv(path,source='MOCK OBSERVED LABELS FOR UNIT TEST ONLY',license_name='CC0 test fixture',collected_on='2026-11-05',mode='real_observed',db_path=db)
 artifact=tmp_path/'model.json';result=evaluate(key,db_path=db,train_model=True,artifact_path=artifact)
 saved=json.loads(artifact.read_text());validate_artifact(saved)
 assert saved['serving_enabled'] is False and result['ml_enabled'] is False
 assert 'ridge_candidate' in result['methods']

def test_profile_change_preserves_clock_and_generation():
 generation=sim.generation;sim.started-=90
 client.post('/api/demo/scenario',json={'scenario':'normal','demand_profile':'evening','preserve_clock':True})
 assert sim.generation==generation and sim.state()[0]>=90
