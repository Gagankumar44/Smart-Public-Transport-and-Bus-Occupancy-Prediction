"""Isolated mock GTFS/GTFS-RT. These tests never contact a live provider."""
import sqlite3
import zipfile
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient
from google.transit import gtfs_realtime_pb2 as g
from app import main,network,feeds,pilot_store as store,intelligence

@pytest.fixture
def monitor(tmp_path,monkeypatch):
 archive=tmp_path/'network.zip'
 with zipfile.ZipFile(archive,'w') as z:
  z.writestr('stops.txt','stop_id,stop_name,stop_lat,stop_lon\na,Alpha,12.9,77.6\nb,Beta,12.91,77.61\nc,Charlie,12.92,77.62\n')
  z.writestr('routes.txt','route_id,route_short_name,route_long_name\nr,501,Alpha Charlie\n')
  z.writestr('trips.txt','route_id,service_id,trip_id,direction_id\nr,s,primary,0\nr,s,alternative,0\n')
  z.writestr('stop_times.txt','trip_id,stop_id,stop_sequence,arrival_time,departure_time\nprimary,a,1,09:00:00,09:00:00\nprimary,b,2,09:10:00,09:10:00\nprimary,c,3,09:20:00,09:20:00\nalternative,a,1,09:01:00,09:01:00\nalternative,b,2,09:18:00,09:18:00\nalternative,c,3,09:23:00,09:23:00\n')
  z.writestr('calendar_dates.txt','service_id,date,exception_type\ns,20261106,1\n')
 report=network.import_network(archive,tmp_path/'versions')
 monkeypatch.setenv('GTFS_DB_PATH',report['path']);monkeypatch.setenv('RUSHLESS_DATA_MODE','authorized');monkeypatch.setenv('RUSHLESS_SOURCE_ID','mock-provider');monkeypatch.setenv('TRANSIT_FEED_AUTHORIZED','true')
 monkeypatch.setattr(main,'STOPS',network.stops())
 feeds.cached_trip.cache_clear();feeds.ROUTE_CACHE.clear();intelligence.watches.clear()
 clock=[datetime(2026,11,6,9,5,tzinfo=ZoneInfo('Asia/Kolkata'))]
 monkeypatch.setattr(store,'now',lambda:clock[0])
 with sqlite3.connect(report['path']) as db:rid=db.execute('SELECT id FROM network_patterns LIMIT 1').fetchone()[0]
 yield dict(clock=clock,rid=rid,db=report['path'],client=TestClient(main.app))
 feeds.cached_trip.cache_clear();feeds.ROUTE_CACHE.clear();intelligence.watches.clear()

def feed(m,delay=300,cancelled=False,speed=5):
 message=g.FeedMessage();message.header.gtfs_realtime_version='2.0';message.header.timestamp=int(m['clock'][0].timestamp())
 e=message.entity.add();e.id='position';v=e.vehicle;v.trip.trip_id='primary';v.trip.route_id='r';v.trip.direction_id=0;v.trip.start_date='20261106';v.vehicle.id='MOCK-BUS';v.timestamp=message.header.timestamp
 fraction=.5 if m['clock'][0].minute<10 else 1.2
 v.position.latitude=12.9+fraction*.01;v.position.longitude=77.6+fraction*.01
 if speed is not None:v.position.speed=speed
 v.position.bearing=45
 e=message.entity.add();e.id='update';u=e.trip_update;u.trip.CopyFrom(v.trip);u.timestamp=v.timestamp;u.vehicle.id=v.vehicle.id;u.delay=delay
 if cancelled:u.trip.schedule_relationship=g.TripDescriptor.CANCELED
 return feeds.ingest(message.SerializeToString(),sid='mock-provider',provenance='Isolated mock provider test; not a real observation',license_name='Test fixture',source_mode='authorized',path=m['db'])

def test_route_stop_monitor_exposes_fresh_gps_movement_and_updated_arrivals(monitor):
 m=monitor;assert feed(m)['accepted']==2
 result=m['client'].get('/api/routes/'+m['rid']+'/monitor?stop_index=1')
 assert result.status_code==200
 data=result.json();assert data['live_connected'] and data['positioned_buses']==1 and data['moving_buses']==1
 assert data['vehicles'][0]['speed_kmh']==18 and data['vehicles'][0]['movement']=='moving'
 assert data['stop']['id']=='b'
 assert datetime.fromisoformat(data['arrivals'][0]['arrival_at']).astimezone(ZoneInfo('Asia/Kolkata')).strftime('%H:%M')=='09:15'
 assert data['arrivals'][0]['metadata']['source']=='real_observed'
 # Origin departures have passed, but the selected downstream stop remains eligible.
 assert any(a['trip_id']=='alternative' and a['metadata']['source']=='schedule' for a in data['arrivals'])
 assert m['client'].get('/api/routes/'+m['rid']+'/monitor?stop_index=99').status_code==422

def test_stale_positions_do_not_claim_moving_buses_or_keep_old_gps(monitor):
 m=monitor;feed(m);m['clock'][0]+=timedelta(seconds=121)
 data=m['client'].get('/api/routes/'+m['rid']+'/monitor?stop_index=1').json()
 assert not data['live_connected'] and data['moving_buses'] is None and data['vehicles']==[]
 assert data['arrivals'] and all(a['metadata']['source']=='schedule' for a in data['arrivals'])

@pytest.mark.parametrize('speed',[-1,100,float('nan')])
def test_invalid_provider_speed_does_not_make_a_bus_marker(monitor,speed):
 m=monitor;assert feed(m,speed=speed)['rejected']==1
 state=m['client'].get('/api/routes/'+m['rid']+'/monitor?stop_index=1').json()
 assert state['vehicles']==[] and state['moving_buses'] is None

def test_stationary_provider_speed_is_kept_distinct_from_moving(monitor):
 m=monitor;feed(m,speed=0)
 state=m['client'].get('/api/routes/'+m['rid']+'/monitor?stop_index=1').json()
 assert state['moving_buses']==0 and state['stationary_buses']==1

def test_route_search_handles_number_punctuation_and_never_substitutes_unrelated_routes(monitor):
 m=monitor;feed(m);c=m['client']
 assert c.get('/api/routes?q=50-1').json()[0]['name']=='501'
 assert c.get('/api/routes?q=nonexistent-route').json()==[]

def test_repeated_stop_occurrence_uses_its_own_later_arrival(monitor):
 m=monitor
 with sqlite3.connect(m['db']) as db:
  db.execute("UPDATE stop_times SET seq=4,stop_sequence='4' WHERE stop_id='c'")
  for trip,seconds in [('primary',9*3600+15*60),('alternative',9*3600+20*60)]:
   time=f'{seconds//3600:02}:{seconds%3600//60:02}:00'
   db.execute('INSERT INTO stop_times(trip_id,stop_id,stop_sequence,arrival_time,departure_time,arrival_seconds,departure_seconds,seq) VALUES (?,?,?,?,?,?,?,?)',(trip,'a','3',time,time,seconds,seconds,3))
 feeds.cached_trip.cache_clear();feeds.ROUTE_CACHE.clear()
 state=m['client'].get('/api/routes/'+m['rid']+'/monitor?stop_index=2').json()
 assert state['stop']['id']=='a' and state['arrivals']
 assert datetime.fromisoformat(state['arrivals'][0]['arrival_at']).strftime('%H:%M')=='09:15'

def test_search_ranks_candidates_before_loading_map_geometry(monitor,monkeypatch):
 m=monitor;feed(m);calls=[]
 monkeypatch.setattr(network,'geometry',lambda *args: calls.append(args[0]) or [[12.91,77.61],[12.92,77.62]])
 result=m['client'].get('/api/journeys?origin=b&destination=c&limit=1').json()
 assert len(result['journeys'])==1 and len(calls)==1
 assert len(result['journeys'][0]['geometry'])==2

def test_missing_speed_does_not_invent_movement_and_cancelled_trip_stays_out(monitor):
 m=monitor;feed(m,speed=None)
 data=m['client'].get('/api/routes/'+m['rid']+'/monitor?stop_index=1').json()
 assert data['moving_buses']==0 and data['movement_unknown']==1
 m['clock'][0]+=timedelta(seconds=1);feed(m,cancelled=True)
 data=m['client'].get('/api/routes/'+m['rid']+'/monitor?stop_index=1').json()
 assert all(a['trip_id']!='primary' for a in data['arrivals'])
 assert data['positioned_buses']==0

def test_after_boarding_new_provider_delay_updates_destination_and_reroutes(monitor):
 m=monitor;feed(m);c=m['client']
 response=c.post('/api/watches',json=dict(trip_id='primary',origin='b',destination='c',preference='fastest'))
 assert response.status_code==201
 path='/api/watches/'+response.json()['id']
 onboard=c.patch(path+'/progress',json={'current_stop':'b','phase':'onboard'}).json()
 assert onboard['current']['wait_minutes']==0
 m['clock'][0]+=timedelta(minutes=11);feed(m,delay=600)
 changed=c.get(path+'?preference=fastest').json()
 assert changed['available'] and changed['phase']=='onboard'
 assert datetime.fromisoformat(changed['current']['arrival_at'])>datetime.fromisoformat(onboard['current']['arrival_at'])
 assert any(a['kind']=='delay' for a in changed['alerts'])
 assert changed['alternative']['id']=='alternative' and changed['alternative']['origin']['id']=='b'
 m['clock'][0]+=timedelta(seconds=1);feed(m,cancelled=True)
 cancelled=c.get(path+'?preference=fastest').json()
 assert not cancelled['available'] and cancelled['alternative']['id']=='alternative'
 accepted=c.post(path+'/decision',json={'action':'accept'}).json()
 assert accepted['trip_id']=='alternative' and accepted['phase']=='waiting'
