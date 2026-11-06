import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi.testclient import TestClient
from app.main import app,sim,flow,crowd
from app.import_gtfs import seconds
client=TestClient(app)
def reset(scenario='normal'):
 return client.post('/api/demo/scenario',json={'scenario':scenario})
def search(mode='comfortable',**kwargs):
 return client.get('/api/journeys',params={'origin':'silk','destination':'marathahalli','preference':mode,**kwargs})
def test_core_flow_and_preferences():
 reset(); assert client.get('/api/health').status_code==200
 assert 'bellandur' in client.get('/api/stops/search?q=bell').json()[0]['name'].lower()
 comfortable=search().json()['journeys'];fastest=search('fastest').json()['journeys']
 assert len(comfortable)==3
 assert comfortable[0]['route_id']=='demo-2'
 assert fastest[0]['route_id']=='demo-1'
 for j in comfortable:
  assert j['origin']['id']=='silk' and j['destination']['id']=='marathahalli'
  assert len(j['geometry'])==j['stop_count']+1
  assert j['metadata']['source']=='simulation'
def test_validation_and_reverse():
 assert client.get('/api/journeys?origin=silk&destination=silk').status_code==422
 assert client.get('/api/journeys?origin=bad&destination=silk').status_code==404
 assert search('invalid').status_code==422
 assert len(search(origin='marathahalli',destination='silk').json()['journeys'])>=2
def test_eta_progress_and_passed_stop():
 reset();before=search('fastest').json()['journeys'][0]['wait_minutes']
 sim.started-=60
 after=search('fastest').json()['journeys'][0]['wait_minutes']
 assert before-after>=.9
 sim.started-=300
 assert all(j['vehicle_id']!='SIM-10' for j in search().json()['journeys'])
def test_missing_and_traffic():
 reset();normal=search().json()['journeys'][0]['total_minutes']
 reset('traffic');heavy=search().json()['journeys'][0]['total_minutes']
 assert heavy>normal
 reset('missing')
 for j in search().json()['journeys']:
  assert j['crowding']=='Unknown' and j['metadata']['confidence']=='Low'
  assert j['metadata']['source']=='schedule'
def test_capacity_and_thresholds():
 for current in [0,5,40,60]:
  for index in range(10):
   assert 0<=flow(current,index,0,'peak')<=60
 assert [crowd(x) for x in [.39,.4,.75,.76]]==['Low','Moderate','Moderate','High']
 assert seconds('25:10:00')==90600
def test_vehicle_and_arrival_consistency():
 reset();j=search().json()['journeys'][0]
 p=client.get(f'/api/vehicles/{j["vehicle_id"]}/occupancy?stop_id=silk').json()
 assert p['crowding']==j['crowding'] and abs(p['minutes']-j['wait_minutes'])<.2
 assert client.get('/api/vehicles/invalid').status_code==404
 assert client.post('/api/demo/scenario',json={'scenario':'invalid'}).status_code==422
def test_disable_demo_controls(monkeypatch):
 monkeypatch.setenv('ENABLE_DEMO_CONTROLS','false')
 assert reset().status_code==403

def test_gtfs_import_and_validation(tmp_path):
 import zipfile,sqlite3
 from app.import_gtfs import import_feed
 feed=tmp_path/'feed.zip'; db=tmp_path/'feed.db'
 with zipfile.ZipFile(feed,'w') as z:
  z.writestr('stops.txt','stop_id,stop_name,stop_lat,stop_lon\na,Test,12.9,77.6\n')
  z.writestr('routes.txt','route_id,route_short_name\nr,Test\n')
  z.writestr('trips.txt','route_id,service_id,trip_id,direction_id\nr,s,t,1\n')
  z.writestr('stop_times.txt','trip_id,stop_id,stop_sequence,arrival_time,departure_time\nt,a,1,25:10:00,25:11:00\n')
  z.writestr('calendar_dates.txt','service_id,date,exception_type\ns,20261105,1\n')
 import_feed(feed,db)
 with sqlite3.connect(db) as conn:
  assert conn.execute('select arrival_time_seconds from stop_times').fetchone()[0]==90600
  assert conn.execute('select direction_id from trips').fetchone()[0]=='1'
 import pytest
 with zipfile.ZipFile(tmp_path/'bad.zip','w') as z: z.writestr('empty.txt','')
 with pytest.raises(ValueError): import_feed(tmp_path/'bad.zip',tmp_path/'bad.db')

def test_projection_is_stop_specific_and_deterministic():
 reset(); first=client.get('/api/vehicles/SIM-20/occupancy?stop_id=silk').json()
 later=client.get('/api/vehicles/SIM-20/occupancy?stop_id=marathahalli').json()
 assert first['utilization']!=later['utilization']
 reset(); again=client.get('/api/vehicles/SIM-20/occupancy?stop_id=silk').json()
 assert first['crowding']==again['crowding'] and first['utilization']==again['utilization']
 reset('peak'); peak=client.get('/api/vehicles/SIM-20/occupancy?stop_id=silk').json()
 assert peak['utilization']>first['utilization']
