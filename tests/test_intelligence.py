import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text
from app.main import app,sim,engine
from app import main
from app.intelligence import rate_buckets,watches,classify_gap,evaluate_alerts

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
 monkeypatch.setattr(main,'engine',create_engine('sqlite:///'+str(tmp_path/'test.db')))
 with main.engine.begin() as db:db.execute(text('CREATE TABLE scenario_events (at TEXT, scenario TEXT)'))
 sim.reset('normal');rate_buckets.clear();watches.clear()
 yield
 sim.reset('normal')

def report(client,level='High',vehicle='SIM-20',**kw):
 return client.post('/api/crowd-reports',json=dict(vehicle_id=vehicle,route_id='demo-2',trip_id='demo-2-trip-0',stop_id='silk',level=level,generation=sim.generation,**kw))
def options():return TestClient(app).get('/api/journeys?origin=silk&destination=marathahalli').json()['journeys']
def forecast(vid='SIM-20'):return TestClient(app).get(f'/api/vehicles/{vid}/occupancy?stop_id=silk').json()
def watch(c):return c.post('/api/watches',json=dict(trip_id='demo-2-trip-0',origin='silk',destination='marathahalli',preference='comfortable')).json()['id']

def test_reports_validate_store_blend_and_limit():
 c=TestClient(app);before=forecast();other=forecast('SIM-30')
 assert report(c).status_code==201
 after=forecast();assert after['utilization']>before['utilization']
 assert after['metadata']['report_count']==1
 assert after['metadata']['base_utilization']==before['metadata']['base_utilization']
 assert forecast('SIM-30')['utilization']==other['utilization']
 assert c.get('/api/crowd-reports/summary').json()['count']==1
 assert report(c).status_code==429
 assert report(TestClient(app),vehicle='bad').status_code==404
 assert report(TestClient(app),level='bad').status_code==422

def test_expiration_conflicts_and_generation():
 assert report(TestClient(app),'High').status_code==201
 assert report(TestClient(app),'Low').status_code==201
 assert forecast()['metadata']['report_conflict']
 assert forecast()['metadata']['confidence']=='Low'
 with main.engine.begin() as db:db.execute(text("UPDATE crowd_reports SET created_at='2020-01-01T08:30:00+05:30'"))
 assert forecast()['metadata']['report_count']==0
 assert TestClient(app).get('/api/crowd-reports/summary').json()['count']==0
 sim.reset('normal');assert forecast()['metadata']['report_count']==0

def test_watch_delay_alternative_accept_stop():
 c=TestClient(app);key=watch(c);before=c.get('/api/watches/'+key).json();assert before['current']['route_id']=='demo-2'
 assert c.post('/api/demo/scenario',json={'scenario':'traffic'}).status_code==200
 state=c.get('/api/watches/'+key).json()
 assert any(a['kind']=='delay' for a in state['alerts'])
 assert state['alternative'] and state['trip_id']=='demo-2-trip-0'
 count=len(state['alerts']);assert len(c.get('/api/watches/'+key).json()['alerts'])==count
 accepted=c.post('/api/watches/'+key+'/decision',json={'action':'accept'}).json()
 assert accepted['trip_id']!='demo-2-trip-0'
 assert c.delete('/api/watches/'+key).status_code==204
 assert c.get('/api/watches/'+key).status_code==404

def test_keep_reset_stale_and_crowd_alerts():
 c=TestClient(app);key=watch(c)
 c.post('/api/demo/scenario',json={'scenario':'traffic'})
 assert c.get('/api/watches/'+key).json()['alternative']
 assert c.post('/api/watches/'+key+'/decision',json={'action':'keep'}).json()['alternative'] is None
 c.post('/api/demo/scenario',json={'scenario':'peak'})
 assert any(a['kind']=='crowding' for a in c.get('/api/watches/'+key).json()['alerts'])
 c.post('/api/demo/scenario',json={'scenario':'missing'})
 assert c.get('/api/watches/'+key).json()['current']['crowding']=='Unknown'
 c.post('/api/demo/scenario',json={'scenario':'normal','restart':True})
 assert c.get('/api/watches/'+key).json()['generation']==sim.generation

def test_headways_and_passed_bus():
 c=TestClient(app);assert c.get('/api/stops/silk/close-arrivals').json()==[]
 c.post('/api/demo/scenario',json={'scenario':'close'})
 result=c.get('/api/stops/silk/close-arrivals').json();assert len(result)==1
 assert result[0]['gap_minutes']==2 and result[0]['route_id']=='demo-1'
 assert result[0]['first']['route_id']==result[0]['second']['route_id']
 assert classify_gap(2,2)=='Close arrivals'
 assert classify_gap(2,None)=='Close arrivals'
 assert classify_gap(10,25) is None
 sim.started-=500
 assert c.get('/api/stops/silk/close-arrivals').json()==[]

def test_thresholds_dedup_and_small_changes():
 c=TestClient(app);key=watch(c)
 sim.started-=250
 state=c.get('/api/watches/'+key).json();assert any(a['kind']=='approaching-5' for a in state['alerts'])
 assert len(c.get('/api/watches/'+key).json()['alerts'])==len(state['alerts'])
 sim.started-=200
 assert any(a['kind']=='approaching-2' for a in c.get('/api/watches/'+key).json()['alerts'])
 sim.started-=200
 assert not c.get('/api/watches/'+key).json()['available']
 from app.intelligence import materially_better
 j=options()[0];tiny={**j,'score':j['score']-.001,'total_minutes':j['total_minutes']-.1}
 assert not materially_better(j,tiny,'comfortable')

def test_insights_and_trip_validation():
 c=TestClient(app);data=c.get('/api/insights/summary').json()
 assert data['source']=='simulation' and data['active_vehicles']==sum(r['vehicles'] for r in data['routes'])
 assert c.post('/api/watches',json=dict(trip_id='bad',origin='silk',destination='marathahalli')).status_code==409
 assert c.get('/api/stops/bad/close-arrivals').status_code==404

def test_revised_reports_do_not_multiply_independent_sources():
 c=TestClient(app);assert report(c).status_code==201
 with main.engine.begin() as db:
  db.execute(text("INSERT INTO crowd_reports SELECT 'revision',generation,vehicle_id,route_id,trip_id,stop_id,'Low',created_at,client,source FROM crowd_reports LIMIT 1"))
 assert forecast()['metadata']['report_count']==1
 assert forecast()['metadata']['report_conflict'] is False
