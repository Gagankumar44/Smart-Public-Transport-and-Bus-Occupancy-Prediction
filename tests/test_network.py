import zipfile,sqlite3,json
import pytest
from app import network

def feed(path,bad=False):
 with zipfile.ZipFile(path,'w') as z:
  z.writestr('stops.txt','stop_id,stop_name,stop_lat,stop_lon\na,Alpha,12.9,77.6\nb,Beta,12.91,77.61\n')
  z.writestr('routes.txt','route_id,route_short_name,route_long_name\nr,REAL,Alpha Beta\n')
  z.writestr('trips.txt','route_id,service_id,trip_id,direction_id,shape_id\nr,s,t,1,sh\n')
  z.writestr('stop_times.txt','trip_id,stop_id,stop_sequence,arrival_time,departure_time\nt,a,1,25:00:00,25:00:00\nt,b,2,'+('24:00:00' if bad else '25:10:00')+',25:10:00\n')
  z.writestr('calendar_dates.txt','service_id,date,exception_type\ns,20261105,1\n')
  z.writestr('feed_info.txt','feed_version\nfixture\n')
  z.writestr('shapes.txt','shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nsh,12.9,77.6,1\nsh,12.91,77.61,2\n')
def test_versioned_network_preserves_ids_and_midnight(tmp_path,monkeypatch):
 archive=tmp_path/'feed.zip';feed(archive);monkeypatch.setattr(network,'MANIFEST',tmp_path/'active.json')
 report=network.import_network(archive,tmp_path/'versions',True)
 assert report['trips']==1 and report['patterns']==1 and report['license'].startswith('ODbL')
 with sqlite3.connect(report['path']) as db:
  assert db.execute('SELECT arrival_seconds FROM stop_times ORDER BY seq').fetchall()==[(90000,),(90600,)]
  assert db.execute('SELECT direction_id FROM trips').fetchone()[0]=='1'
 assert json.loads(network.MANIFEST.read_text())['sha256']==report['sha256']
 before=network.MANIFEST.read_bytes()
 with pytest.raises(ValueError):network.import_network(archive,tmp_path/'versions',True)
 assert network.MANIFEST.read_bytes()==before

def test_invalid_update_does_not_replace_active_network(tmp_path,monkeypatch):
 monkeypatch.setattr(network,'MANIFEST',tmp_path/'active.json');good=tmp_path/'good.zip';feed(good);network.import_network(good,tmp_path/'versions',True);before=network.MANIFEST.read_bytes()
 bad=tmp_path/'bad.zip';feed(bad,True)
 with pytest.raises(ValueError,match='No valid trips'):network.import_network(bad,tmp_path/'versions',True)
 assert network.MANIFEST.read_bytes()==before
 assert not list((tmp_path/'versions').glob('*.pending'))

def test_shape_read_and_stop_aliases(tmp_path,monkeypatch):
 archive=tmp_path/'feed.zip';feed(archive);r=network.import_network(archive,tmp_path/'versions');monkeypatch.setenv('GTFS_DB_PATH',r['path'])
 assert network.geometry('t')==[[12.9,77.6],[12.91,77.61]]
 assert [s['gtfs_stop_id'] for s in network.stops()]==['a','b']

def test_route_departures_respect_midnight_and_service_calendar(tmp_path,monkeypatch):
 from datetime import datetime
 from zoneinfo import ZoneInfo
 from fastapi.testclient import TestClient
 from app.main import app
 archive=tmp_path/'feed.zip';feed(archive)
 report=network.import_network(archive,tmp_path/'versions');monkeypatch.setenv('GTFS_DB_PATH',report['path'])
 with sqlite3.connect(report['path']) as db:pattern=db.execute('SELECT id FROM network_patterns').fetchone()[0]
 clock=datetime(2026,11,6,0,30,tzinfo=ZoneInfo('Asia/Kolkata'))
 departures=network.departures(pattern,clock)
 assert len(departures)==1
 assert departures[0]['service_date']=='20261105'
 assert departures[0]['departure_at']=='2026-11-06T01:00:00+05:30'
 assert departures[0]['arrival_at']=='2026-11-06T01:10:00+05:30'
 assert departures[0]['source']=='schedule' and 'lat' not in departures[0]
 assert network.departures(pattern,clock.replace(hour=2))==[]
 assert network.departures('unknown',clock) is None
 client=TestClient(app)
 assert client.get('/api/routes/unknown/departures').status_code==404
 assert client.get('/api/routes/'+pattern+'/departures?limit=0').status_code==422
 assert client.get('/api/routes/'+pattern+'/departures').json()['source']=='schedule'

def test_departure_browser_checks_next_week_without_inventing_service(tmp_path,monkeypatch):
 from datetime import datetime
 from zoneinfo import ZoneInfo
 archive=tmp_path/'feed.zip';feed(archive)
 report=network.import_network(archive,tmp_path/'versions');monkeypatch.setenv('GTFS_DB_PATH',report['path'])
 with sqlite3.connect(report['path']) as db:
  pattern=db.execute('SELECT id FROM network_patterns').fetchone()[0]
  db.execute("UPDATE calendar_dates SET date='20261108'")
 clock=datetime(2026,11,6,12,tzinfo=ZoneInfo('Asia/Kolkata'))
 result=network.departures(pattern,clock)
 assert len(result)==1 and result[0]['departure_at']=='2026-11-09T01:00:00+05:30'
 with sqlite3.connect(report['path']) as db:db.execute("UPDATE calendar_dates SET exception_type='2'")
 assert network.departures(pattern,clock)==[]

def test_worker_backs_off_without_leaking_errors(monkeypatch,capsys):
 from app.feed_worker import poll
 monkeypatch.setenv('TRANSIT_POLL_SECONDS','30');delays=[];calls=[]
 def fail():
  calls.append(1)
  raise ValueError('private token example')
 poll(3,fetch=fail,wait=delays.append)
 assert len(calls)==3 and delays==[60,120]
 assert 'private token' not in capsys.readouterr().out

def test_network_status_never_claims_simulation_is_live():
 from fastapi.testclient import TestClient
 from app.main import app
 response=TestClient(app).get('/api/network/status')
 assert response.status_code==200
 assert response.json()['live_connected'] is False
 assert 'matched_vehicle_count' in response.json()

def test_public_mode_cannot_enable_demo(monkeypatch):
 from app import feeds
 from app.main import app
 from fastapi.testclient import TestClient
 monkeypatch.delenv('RUSHLESS_TEST_MODE',raising=False)
 monkeypatch.setenv('RUSHLESS_DATA_MODE','simulation')
 assert feeds.mode()=='schedule'
 assert TestClient(app).post('/api/demo/scenario',json={'scenario':'normal'}).status_code==403

def test_schedule_preview_coalesces_concurrent_requests(tmp_path,monkeypatch):
 from app import feeds
 import concurrent.futures,time
 registry=tmp_path/'registry.db';registry.touch()
 monkeypatch.setattr(feeds,'registry_path',lambda:registry)
 monkeypatch.setattr(feeds,'mode',lambda:'schedule')
 calls=[]
 def build():
  calls.append(1);time.sleep(.03);return (0,'clock',[])
 monkeypatch.setattr(feeds,'build_external_snapshot',build);feeds.PREVIEW_CACHE.clear()
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  values=list(pool.map(lambda _:feeds.external_snapshot(),range(6)))
 assert len(calls)==1 and all(value==values[0] for value in values)
 feeds.PREVIEW_CACHE.clear()

def test_future_schedule_planning_uses_calendar(tmp_path,monkeypatch):
 from app import feeds,main
 from fastapi.testclient import TestClient
 from datetime import datetime,timedelta
 from zoneinfo import ZoneInfo
 import sqlite3
 path,_=feeds.fixture(tmp_path)
 tomorrow=datetime.now(ZoneInfo('Asia/Kolkata')).replace(hour=8,minute=55,second=0,microsecond=0)+timedelta(days=1)
 with sqlite3.connect(path) as db:
  db.execute('DELETE FROM calendar_dates');db.execute('INSERT INTO calendar_dates VALUES (?,?,?)',('fixture-service',tomorrow.strftime('%Y%m%d'),'1'))
  for index,stop in enumerate(main.STOPS):
   seconds=9*3600+index*180;db.execute('UPDATE stop_times SET arrival_time=? WHERE stop_id=?',(f'{seconds//3600:02}:{seconds%3600//60:02}:00',stop['id']))
 monkeypatch.setenv('RUSHLESS_DATA_MODE','schedule');monkeypatch.setenv('GTFS_DB_PATH',str(path))
 result=TestClient(main.app).get('/api/journeys',params={'origin':'silk','destination':'marathahalli','depart_at':tomorrow.isoformat()})
 assert result.status_code==200 and result.json()['journeys']
 for journey in result.json()['journeys']:
  assert journey['metadata']['source']=='schedule' and journey['crowding']=='Unknown'
  assert datetime.fromisoformat(journey['boarding_at'])>=tomorrow
 invalid=TestClient(main.app).get('/api/journeys',params={'origin':'silk','destination':'marathahalli','depart_at':tomorrow.replace(tzinfo=None).isoformat()})
 assert invalid.status_code==422

def test_published_fares_require_matching_zone_and_direction(tmp_path,monkeypatch):
 import sqlite3
 from app import network
 path=tmp_path/'fares.db'
 with sqlite3.connect(path) as db:
  db.executescript('''CREATE TABLE stops(stop_id TEXT,zone_id TEXT);CREATE TABLE routes(route_id TEXT,route_short_name TEXT);CREATE TABLE network_patterns(id TEXT,trip_id TEXT,route_id TEXT);CREATE TABLE stop_times(trip_id TEXT,stop_id TEXT,seq INTEGER);CREATE TABLE fare_rules(fare_id TEXT,route_id TEXT,origin_id TEXT,destination_id TEXT);CREATE TABLE fare_attributes(fare_id TEXT,price TEXT,currency_type TEXT);''')
  db.executemany('INSERT INTO stops VALUES (?,?)',[('a','A'),('b','B')]);db.execute("INSERT INTO routes VALUES ('r','Published route')");db.execute("INSERT INTO network_patterns VALUES ('p','t','r')");db.executemany('INSERT INTO stop_times VALUES (?,?,?)',[('t','a',1),('t','b',2)]);db.execute("INSERT INTO fare_rules VALUES ('F35','r','A','B')");db.execute("INSERT INTO fare_attributes VALUES ('F35','35.00','INR')")
 monkeypatch.setenv('GTFS_DB_PATH',str(path))
 assert network.fares('a','b')==[dict(route_id='r',route_name='Published route',fare_id='F35',amount=35.0,currency='INR')]
 assert network.fares('b','a')==[]
