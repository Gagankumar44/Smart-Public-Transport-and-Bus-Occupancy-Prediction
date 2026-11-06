"""Controlled GTFS engineering fixtures, not claims about actual BMTC trips."""
import sqlite3
import zipfile
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient
from app import main,network,feeds,explorer

@pytest.fixture
def route_case(tmp_path,monkeypatch):
 day=(datetime.now(ZoneInfo('Asia/Kolkata'))+timedelta(days=1)).replace(hour=9,minute=0,second=0,microsecond=0)
 archive=tmp_path/'controlled-network.zip'
 routes=[('S','SHORT',['a','b','c'],['09:20:00','09:40:00','10:00:00'],'s'),('F','FAST',['a','d','c'],['09:02:00','09:10:00','09:20:00'],'s'),('T1','CHANGE 1',['a','b'],['09:01:00','09:08:00'],'s'),('T2','CHANGE 2',['b','c'],['09:12:00','09:23:00'],'s'),('R','REVERSE',['c','b','a'],['09:10:00','09:20:00','09:30:00'],'s'),('E','DEPARTED',['a','c'],['08:40:00','08:55:00'],'s'),('I','INACTIVE',['a','c'],['09:01:00','09:02:00'],'off')]
 coords={'a':(12.9,77.6),'b':(12.9,77.61),'c':(12.9,77.62),'d':(12.91,77.61)}
 with zipfile.ZipFile(archive,'w') as z:
  z.writestr('stops.txt','stop_id,stop_name,stop_lat,stop_lon\n'+''.join(f'{sid},{sid.upper()},{lat},{lon}\n' for sid,(lat,lon) in coords.items()))
  z.writestr('routes.txt','route_id,route_short_name,route_long_name\n'+''.join(f'{rid},{name},{name}\n' for rid,name,*_ in routes))
  z.writestr('trips.txt','route_id,service_id,trip_id,direction_id,shape_id\n'+''.join(f'{rid},{service},trip-{rid},0,shape-{rid}\n' for rid,name,ids,times,service in routes))
  z.writestr('stop_times.txt','trip_id,stop_id,stop_sequence,arrival_time,departure_time,pickup_type,drop_off_type\n'+''.join(f'trip-{rid},{sid},{i+1},{time},{time},0,0\n' for rid,name,ids,times,service in routes for i,(sid,time) in enumerate(zip(ids,times))))
  z.writestr('calendar_dates.txt',f'service_id,date,exception_type\ns,{day:%Y%m%d},1\noff,{day:%Y%m%d},2\n')
  z.writestr('shapes.txt','shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n'+''.join(f'shape-{rid},{coords[sid][0]},{coords[sid][1]},{i+1}\n' for rid,name,ids,times,service in routes for i,sid in enumerate(ids)))
 report=network.import_network(archive,tmp_path/'versions')
 monkeypatch.setenv('GTFS_DB_PATH',report['path']);monkeypatch.setenv('RUSHLESS_DATA_MODE','schedule')
 monkeypatch.setattr(main,'STOPS',network.stops());feeds.cached_trip.cache_clear();feeds.stop_maps.cache_clear();feeds.ROUTE_CACHE.clear();explorer.SNAPSHOTS.clear()
 case=dict(client=TestClient(main.app),day=day,path=report['path'],params=dict(origin='a',destination='c',depart_at=day.isoformat(),limit=20))
 yield case
 explorer.SNAPSHOTS.clear();feeds.cached_trip.cache_clear();feeds.stop_maps.cache_clear();feeds.ROUTE_CACHE.clear()

def get(case,**overrides):
 response=case['client'].get('/api/journeys/explore',params={**case['params'],**overrides})
 assert response.status_code==200,response.text
 return response.json()

def test_shape_distance_shortest_and_fastest_are_distinct(route_case):
 c=route_case;short=get(c,sort='shortest');fast=get(c,sort='fastest',search_id=short['search_id'])
 assert short['total']>3
 assert short['journeys'][0]['distance_km']<fast['journeys'][0]['distance_km']
 assert fast['journeys'][0]['legs'][0]['route_name']=='FAST'
 assert fast['journeys'][0]['total_minutes']==20
 expected=explorer.haversine([12.9,77.6],[12.9,77.61])+explorer.haversine([12.9,77.61],[12.9,77.62])
 assert abs(short['journeys'][0]['distance_km']-expected)<.003
 assert all(j['distance_measured'] for j in short['journeys'])

def test_transfer_is_same_stop_time_feasible_and_wait_is_counted(route_case):
 data=get(route_case);changed=next(j for j in data['journeys'] if [l['route_name'] for l in j['legs']]==['CHANGE 1','CHANGE 2'])
 assert changed['transfers']==1 and changed['transfer_stop']['id']=='b'
 assert changed['boarding_wait_minutes']==1 and changed['transfer_wait_minutes']==4
 assert changed['ride_minutes']==18 and changed['total_minutes']==23
 assert [s['id'] for s in changed['stops']]==['a','b','c'] and changed['walking_km']==0
 assert len(changed['legs'])==2 and changed['geometry'][0]==[12.9,77.6] and changed['geometry'][-1]==[12.9,77.62]
 assert all(l['metadata']['source']=='schedule' for l in changed['legs'])

def test_infeasible_transfer_forbidden_transfer_and_pickup_restrictions(route_case):
 c=route_case
 with sqlite3.connect(c['path']) as db:
  db.execute('CREATE TABLE transfers(from_stop_id TEXT,to_stop_id TEXT,transfer_type TEXT,min_transfer_time TEXT)')
  db.execute("INSERT INTO transfers VALUES ('b','b','3','')")
 data=get(c)
 assert not any(j['transfers'] for j in data['journeys'])
 with sqlite3.connect(c['path']) as db:
  db.execute('DROP TABLE transfers');db.execute("UPDATE stop_times SET pickup_type='1' WHERE trip_id='trip-F' AND stop_id='a'")
 feeds.cached_trip.cache_clear();explorer.timetable.cache_clear()
 data=get(c)
 assert all(j['legs'][0]['route_name']!='FAST' for j in data['journeys'])

def test_direction_service_dates_departed_buses_and_cycles(route_case):
 data=get(route_case)
 assert not any(l['route_name'] in ['REVERSE','INACTIVE','DEPARTED'] for j in data['journeys'] for l in j['legs'])
 assert all(len(j['stops'])==len({s['id'] for s in j['stops']}) for j in data['journeys'])
 assert len({j['id'] for j in data['journeys']})==data['total']
 assert get(route_case,max_transfers=0)['total']<data['total']
 later=(route_case['day']+timedelta(days=1)).isoformat()
 assert get(route_case,depart_at=later)['journeys']==[]

def test_pagination_backend_sorts_and_snapshot_consistency(route_case):
 first=get(route_case,limit=1);second=get(route_case,limit=1,offset=1,search_id=first['search_id'])
 assert first['has_more'] and first['journeys'][0]['id']!=second['journeys'][0]['id']
 assert first['generated_at']==second['generated_at']
 for mode,key in [('fastest',lambda j:j['total_minutes']),('shortest',lambda j:j['distance_km']),('fewest_transfers',lambda j:(j['transfers'],j['total_minutes']))]:
  values=get(route_case,sort=mode,search_id=first['search_id'])['journeys']
  assert [key(j) for j in values]==sorted(key(j) for j in values)
 explorer.SNAPSHOTS[first['search_id']]['expires']=0
 response=route_case['client'].get('/api/journeys/explore',params={**route_case['params'],'search_id':first['search_id']})
 assert response.status_code==409

def test_invalid_input_and_no_route_are_explicit(route_case):
 c=route_case
 for changes in [dict(origin='a',destination='a'),dict(max_transfers=2),dict(sort='invented'),dict(depart_at=c['day'].replace(tzinfo=None).isoformat()),dict(offset=1)]:
  assert c['client'].get('/api/journeys/explore',params={**c['params'],**changes}).status_code==422
 assert c['client'].get('/api/journeys/explore',params={**c['params'],'origin':'unknown'}).status_code==404
 assert get(c,origin='d',destination='a')['journeys']==[]

def test_missing_shape_stays_an_estimate_and_search_cap_is_reported(route_case,monkeypatch):
 monkeypatch.setattr(network,'geometry',lambda *args:[]);explorer.pattern_geometry.cache_clear()
 data=get(route_case)
 assert data['journeys'] and all(not j['distance_measured'] for j in data['journeys'])
 assert not any('Shortest measured' in j['badges'] for j in data['journeys'])
 monkeypatch.setattr(explorer,'MAX_INSTANCES',1)
 assert get(route_case)['coverage']['limited']
 explorer.pattern_geometry.cache_clear()

def test_controlled_delay_changes_fastest_but_not_distance(route_case,monkeypatch):
 """Synthetic injection is confined to this test and labelled as such."""
 before=get(route_case,sort='fastest');distances={j['id']:j['distance_km'] for j in before['journeys']}
 original=explorer.Search.leg
 def delayed(self,*args):
  leg=original(self,*args)
  if leg and leg['route_name']=='FAST':
   leg={**leg,'arrival_at':(datetime.fromisoformat(leg['arrival_at'])+timedelta(minutes=30)).isoformat(),'ride_minutes':leg['ride_minutes']+30,'metadata':{**leg['metadata'],'source':'replay_synthetic'}}
  return leg
 monkeypatch.setattr(explorer.Search,'leg',delayed)
 after=get(route_case,sort='fastest')
 assert after['journeys'][0]['legs'][0]['route_name']!='FAST'
 assert all(j['distance_km']==distances[j['id']] for j in after['journeys'])
 assert any(l['metadata']['source']=='replay_synthetic' for j in after['journeys'] for l in j['legs'])

def test_planner_reuses_transfer_engine_and_keeps_default_contract(route_case):
 c=route_case
 response=c['client'].get('/api/journeys',params={**c['params'],'max_transfers':1,'preference':'fastest'})
 assert response.status_code==200,response.text
 data=response.json();assert data['coverage']['max_transfers']==1
 assert data['journeys'][0]['route_name']=='FAST'
 assert any(j['transfers']==1 and len(j['legs'])==2 for j in data['journeys'])
 assert all(j['metadata'].get('uncertainty') is None for j in data['journeys'])
 old=c['client'].get('/api/journeys',params=c['params'])
 assert old.status_code==200 and all(j['transfers']==0 for j in old.json()['journeys'])

def test_comfort_uses_backend_source_data_without_inventing_crowding(route_case,monkeypatch):
 original=explorer.Search.leg
 def supplied(self,*args):
  leg=original(self,*args)
  if leg and leg['route_name']=='FAST':
   leg={**leg,'crowding':'High','utilization':.95,'metadata':{**leg['metadata'],'source':'replay_synthetic'}}
  elif leg and leg['route_name'].startswith('CHANGE'):
   leg={**leg,'crowding':'Low','utilization':.2,'metadata':{**leg['metadata'],'source':'replay_synthetic'}}
  return leg
 monkeypatch.setattr(explorer.Search,'leg',supplied)
 fastest=get(route_case,sort='fastest');comfortable=get(route_case,sort='comfortable',search_id=fastest['search_id'])
 assert fastest['journeys'][0]['legs'][0]['route_name']=='FAST'
 assert comfortable['journeys'][0]['id']!=fastest['journeys'][0]['id']
 assert any(j['crowding']=='Unknown' for j in comfortable['journeys'])

def test_after_midnight_gtfs_times_use_previous_service_day(route_case):
 c=route_case
 with sqlite3.connect(c['path']) as db:
  db.execute("UPDATE stop_times SET arrival_time='24:10:00',departure_time='24:10:00',arrival_seconds=87000,departure_seconds=87000 WHERE trip_id='trip-F' AND stop_id='a'")
  db.execute("UPDATE stop_times SET arrival_time='24:20:00',departure_time='24:20:00',arrival_seconds=87600,departure_seconds=87600 WHERE trip_id='trip-F' AND stop_id='d'")
  db.execute("UPDATE stop_times SET arrival_time='24:30:00',departure_time='24:30:00',arrival_seconds=88200,departure_seconds=88200 WHERE trip_id='trip-F' AND stop_id='c'")
 explorer.timetable.cache_clear();feeds.cached_trip.cache_clear()
 data=get(c,depart_at=(c['day']+timedelta(days=1)).replace(hour=0,minute=0).isoformat())
 path=next(j for j in data['journeys'] if j['legs'][0]['route_name']=='FAST')
 assert path['total_minutes']==30 and path['boarding_wait_minutes']==10
 assert path['legs'][0]['service_date']==c['day'].strftime('%Y%m%d')

def test_busy_search_does_not_queue_or_block_stop_catalog(route_case):
 explorer.SEARCH_SLOTS.acquire();explorer.SEARCH_SLOTS.acquire()
 try:
  response=route_case['client'].get('/api/journeys/explore',params=route_case['params'])
  assert response.status_code==503 and 'retry' in response.json()['detail']
  assert route_case['client'].get('/api/stops/search').status_code==200
 finally:explorer.SEARCH_SLOTS.release();explorer.SEARCH_SLOTS.release()
 assert get(route_case)['journeys']

def test_selected_scheduled_trip_resolves_outside_preview_fleet(route_case,monkeypatch):
 c=route_case
 monkeypatch.setattr(main,'snapshot',lambda:(0,datetime.now(ZoneInfo('Asia/Kolkata')),[]))
 vid='scheduled:trip-F:'+c['day'].strftime('%Y%m%d')
 response=c['client'].get('/api/vehicles/'+vid)
 assert response.status_code==200 and response.json()['metadata']['source']=='schedule'
 assert response.json()['lat'] is None and response.json()['lon'] is None
 assert c['client'].get('/api/vehicles/'+vid+'/forecast').status_code==200
 assert c['client'].get('/api/vehicles/scheduled:unknown:20261107').status_code==404

def test_demo_fallback_is_explicit_and_never_replaces_real_results(route_case):
 c=route_case
 empty=get(c,origin='d',destination='a');assert not empty['journeys']
 demo=get(c,origin='d',destination='a',allow_demo=True)
 assert len(demo['journeys'])==3 and demo['coverage']['demo_fallback']
 assert all(j['metadata']['source']=='demo_journey' and not j['distance_measured'] for j in demo['journeys'])
 assert all(j['crowding']=='Unknown' for j in demo['journeys'])
 real=get(c,allow_demo=True)
 assert real['journeys'] and all(j['metadata']['source']=='schedule' for j in real['journeys'])
 response=c['client'].get('/api/journeys',params={**c['params'],'origin':'d','destination':'a','max_transfers':1,'allow_demo':True})
 assert response.status_code==200 and len(response.json()['journeys'])==3
