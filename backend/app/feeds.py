"""Authorized GTFS-RT ingestion, historical replay, normalization and shared serving.

Feed fetching is a local CLI operation, never a public URL-fetch API.
"""
import argparse
import hashlib
import ipaddress
import json
import math
import os
import socket
import sqlite3
from datetime import datetime,timedelta,timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from contextlib import closing
import threading,time
PREVIEW_LOCK=threading.RLock()
PREVIEW_CACHE={}
from google.transit import gtfs_realtime_pb2 as gtfs
from . import pilot_store as store
from .history import instant

ROOT=Path(__file__).resolve().parents[2]
ROUTE_CACHE={}
def mode():
 requested=os.getenv('RUSHLESS_DATA_MODE','schedule')
 return 'schedule' if requested=='simulation' and os.getenv('RUSHLESS_TEST_MODE')!='true' else requested
def source_id():return os.getenv('RUSHLESS_SOURCE_ID','')
def registry_path():
 from .network import active_path
 return active_path()
def distance(a,b):
 lat=(a[0]+b[0])*math.pi/360
 return math.hypot((a[0]-b[0])*111200,(a[1]-b[1])*111200*math.cos(lat))
def project(lat,lon,points):
 best=(float('inf'),0.)
 scale=math.cos(math.radians(lat))
 for index,(a,b) in enumerate(zip(points,points[1:])):
  ax=(a[1]-lon)*scale;ay=a[0]-lat;bx=(b[1]-lon)*scale;by=b[0]-lat
  denominator=(bx-ax)**2+(by-ay)**2;t=max(0,min(1,-(ax*(bx-ax)+ay*(by-ay))/denominator)) if denominator else 0
  d=math.hypot(ax+t*(bx-ax),ay+t*(by-ay))*111200
  if d<best[0]:best=(d,index+t)
 return best
@lru_cache(maxsize=4)
def stop_maps(identity):
 from .main import STOPS
 return ({s.get('gtfs_stop_id',s['id']):s['id'] for s in STOPS},{s['id']:s.get('gtfs_stop_id',s['id']) for s in STOPS})
def alias(sid):
 from .main import STOPS
 return stop_maps(id(STOPS))[0].get(sid,sid)
def original(sid):
 from .main import STOPS
 return stop_maps(id(STOPS))[1].get(sid,sid)

@lru_cache(maxsize=4096)
def cached_trip(path,mtime,trip_id):
 from .import_gtfs import seconds
 with closing(sqlite3.connect('file:'+Path(path).as_posix()+'?mode=ro',uri=True)) as db:
  db.row_factory=sqlite3.Row
  trip=db.execute('SELECT * FROM trips WHERE trip_id=?',(trip_id,)).fetchone()
  if not trip:return None
  route=db.execute('SELECT * FROM routes WHERE route_id=?',(trip['route_id'],)).fetchone()
  times=db.execute('SELECT t.*,s.stop_name,s.stop_lat,s.stop_lon FROM stop_times t JOIN stops s ON s.stop_id=t.stop_id WHERE trip_id=? ORDER BY CAST(stop_sequence AS INTEGER)',(trip_id,)).fetchall()
  if not route or len(times)<2:return None
  from .main import STOPS
  supported=set(stop_maps(id(STOPS))[0])|set(stop_maps(id(STOPS))[1])
  subset=[dict(t) for t in times if t['stop_id'] in supported]
  if len(subset)<2:return None
  for t in subset:
   t['id']=alias(t['stop_id']);t['seconds']=seconds(t['arrival_time']);t['sequence']=int(t['stop_sequence']);t['lat']=float(t['stop_lat']);t['lon']=float(t['stop_lon'])
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  synthetic=bool(db.execute('SELECT synthetic FROM rushless_registry_metadata LIMIT 1').fetchone()[0]) if 'rushless_registry_metadata' in tables else False
  pattern=db.execute('SELECT pattern_id FROM trip_patterns WHERE trip_id=?',(trip_id,)).fetchone()[0] if 'trip_patterns' in tables else None
  return dict(pattern_id=pattern,trip=dict(trip),route=dict(route),times=subset,synthetic=synthetic,origin_time=times[0]['departure_time'] if 'departure_time' in times[0].keys() and times[0]['departure_time'] else times[0]['arrival_time'])
def trip_info(trip_id,path=None):
 path=Path(path or registry_path())
 if not path.exists():return None
 try:return cached_trip(str(path.resolve()),path.stat().st_mtime_ns,trip_id)
 except (sqlite3.Error,ValueError):return None
def logical_route(info):
 route=info['route'];trip=info['trip'];direction=str(trip.get('direction_id') or 'unknown')
 result=dict(id=info.get('pattern_id') or 'gtfs:'+route['route_id']+':'+direction,gtfs_route_id=route['route_id'],trip_id=trip['trip_id'],name=route.get('route_short_name') or route.get('route_long_name') or route['route_id'],direction=direction,stops=[t['id'] for t in info['times']],color='#0d9488',synthetic=info.get('synthetic',False))
 ROUTE_CACHE[result['id']]=result
 return result
def service_stamp(service_date,seconds):return datetime.strptime(service_date,'%Y%m%d').replace(tzinfo=__import__('zoneinfo').ZoneInfo('Asia/Kolkata'))+timedelta(seconds=seconds)

def parse_feed(raw):
 if len(raw)>5_000_000:raise ValueError('Feed exceeds the five-megabyte limit')
 feed=gtfs.FeedMessage()
 try:feed.ParseFromString(raw)
 except Exception as exc:raise ValueError('Invalid GTFS Realtime protobuf') from exc
 if not feed.IsInitialized() or feed.header.gtfs_realtime_version not in ['1.0','2.0']:raise ValueError('Feed header/version is missing or unsupported')
 if feed.header.incrementality!=gtfs.FeedHeader.FULL_DATASET:raise ValueError('Differential feeds require a provider-specific adapter; not applied partially')
 if not feed.header.HasField('timestamp'):raise ValueError('Feed timestamp is required for provenance')
 if feed.header.timestamp>253402300799:raise ValueError('Feed timestamp is outside the supported datetime range')
 records=[]
 entity_ids=set()
 for entity in feed.entity:
  if not entity.id or entity.id in entity_ids:raise ValueError('Feed entity identifiers must be nonempty and unique')
  entity_ids.add(entity.id)
  if entity.is_deleted:continue
  if entity.HasField('alert'):
   alert=entity.alert;selectors=[]
   for selector in alert.informed_entity:
    value={field:getattr(selector,field) for field in ['agency_id','route_id','route_type','stop_id','direction_id'] if selector.HasField(field)}
    if selector.HasField('trip'):
     value['trip']={field:getattr(selector.trip,field) for field in ['trip_id','route_id','direction_id','start_date','start_time'] if selector.trip.HasField(field)}
    selectors.append(value)
   records.append(dict(kind='service_alert',entity_id=entity.id,feed_timestamp=feed.header.timestamp,observed_timestamp=feed.header.timestamp,header=[t.text for t in alert.header_text.translation],description=[t.text for t in alert.description_text.translation],effect=alert.effect,cause=alert.cause,selectors=selectors,active_periods=[{field:getattr(period,field) for field in ['start','end'] if period.HasField(field)} for period in alert.active_period]));continue
  if not entity.HasField('vehicle') and not entity.HasField('trip_update'):continue
  vp=entity.HasField('vehicle');item=entity.vehicle if vp else entity.trip_update;trip=item.trip
  updates=[]
  if not vp:
   for update in item.stop_time_update:
    event=update.arrival if update.arrival.HasField('time') or update.arrival.HasField('delay') else update.departure
    updates.append(dict(stop_id=update.stop_id or None,stop_sequence=update.stop_sequence if update.HasField('stop_sequence') else None,arrival_time=event.time if event.HasField('time') else None,delay=event.delay if event.HasField('delay') else None,relationship=update.schedule_relationship))
  records.append(dict(kind='vehicle_position' if vp else 'trip_update',entity_id=entity.id,vehicle_id=item.vehicle.id or None,trip_id=trip.trip_id or None,route_id=trip.route_id or None,service_date=trip.start_date or None,start_time=trip.start_time or None,direction=trip.direction_id if trip.HasField('direction_id') else None,latitude=item.position.latitude if vp and item.HasField('position') else None,longitude=item.position.longitude if vp and item.HasField('position') else None,observed_timestamp=item.timestamp if item.HasField('timestamp') else (None if vp else feed.header.timestamp),feed_timestamp=feed.header.timestamp,stop_id=item.stop_id or None if vp else None,stop_sequence=item.current_stop_sequence or None if vp else None,stopped=vp and item.current_status==gtfs.VehiclePosition.STOPPED_AT,occupancy_status=item.occupancy_status if vp and item.HasField('occupancy_status') else None,delay=item.delay if not vp and item.HasField('delay') else None,updates=updates,cancelled=trip.schedule_relationship==gtfs.TripDescriptor.CANCELED))
  records[-1]['speed_mps']=item.position.speed if vp and item.position.HasField('speed') else None
  records[-1]['bearing']=item.position.bearing if vp and item.position.HasField('bearing') else None
 return feed.header.timestamp,records

def normalize(record,source,clock,path=None,previous=None):
 flags=[];status='accepted';info=trip_info(record.get('trip_id'),path) if record.get('trip_id') else None
 if record['kind']=='service_alert':
  valid=bool(record.get('selectors')) and all(s for s in record['selectors']) and all(p.get('start',0)<p.get('end',253402300799) for p in record['active_periods']) and record['feed_timestamp']<=clock.timestamp()+30
  return {**record,'source_id':source,'observed_at':datetime.fromtimestamp(record['feed_timestamp'],timezone.utc).isoformat(),'flags':[] if valid else ['Invalid alert selectors, interval or timestamp'],'status':'informational' if valid else 'rejected'}
 if not info:return {**record,'flags':['Unknown or out-of-corridor trip'], 'status':'unmatched'}
 if not record.get('service_date'):return {**record,'flags':['Missing service date; no guessed trip instance'], 'status':'unmatched'}
 try:
  service_day=datetime.strptime(record['service_date'],'%Y%m%d')
  from .schedule import service_active
  with closing(sqlite3.connect(path or registry_path())) as db:
   if not service_active(db,info['trip']['service_id'],service_day):flags.append('Service inactive on this service date')
 except (ValueError,sqlite3.Error):flags.append('Invalid service date or service calendar')
 if record.get('route_id') and record['route_id']!=info['route']['route_id']:flags.append('Trip route mismatch')
 if record.get('start_time'):
  from .import_gtfs import seconds
  try:
   if seconds(record['start_time'])!=seconds(info['origin_time']):flags.append('Trip start time does not match a scheduled instance; frequency matching is unsupported')
  except ValueError:flags.append('Invalid trip start time')
 expected=info['trip'].get('direction_id')
 if record.get('direction') is not None and expected not in [None,''] and str(record['direction'])!=str(expected):flags.append('Trip direction mismatch')
 timestamp=record.get('observed_timestamp')
 if timestamp is None:flags.append('Missing observation timestamp')
 try:observed=datetime.fromtimestamp(timestamp or 0,timezone.utc)
 except (ValueError,OverflowError,OSError):return {**record,'flags':['Observation timestamp is outside the supported datetime range'],'status':'rejected'}
 age=(clock-observed).total_seconds()
 try:
  if not 0<=(observed.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata')).date()-service_day.date()).days<=1:flags.append('Observation outside the trip service instance')
 except UnboundLocalError:pass
 if age< -30:flags.append('Future observation timestamp')
 if record['feed_timestamp']<timestamp if timestamp else False:flags.append('Observation newer than feed timestamp')
 if record['feed_timestamp']>clock.timestamp()+30:flags.append('Future feed timestamp')
 if age>86400:flags.append('Observation more than one day old at source clock')
 lat,lon=record.get('latitude'),record.get('longitude');points=[[t['lat'],t['lon']] for t in info['times']]
 progress=None
 if lat is not None or lon is not None:
  if lat is None or lon is None or not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:flags.append('Invalid geographic coordinates')
  else:
   separation,progress=project(lat,lon,points)
   if separation>1500:flags.append('Location outside supported corridor geometry')
 if record['kind']=='vehicle_position' and not record.get('vehicle_id'):flags.append('Vehicle identifier missing')
 for field,maximum in [('speed_mps',45),('bearing',360)]:
  value=record.get(field)
  if value is not None and (not math.isfinite(value) or not 0<=value<=maximum):flags.append('Invalid provider '+field)
 if record.get('stop_id') and record['stop_id'] not in [t['stop_id'] for t in info['times']]:flags.append('Stop does not belong to supported trip corridor')
 if record.get('stop_sequence') and record['stop_sequence'] not in [t['sequence'] for t in info['times']]:flags.append('Stop sequence outside supported corridor')
 seen=set()
 for update in record.get('updates',[]):
  matches=[t for t in info['times'] if (update['stop_id'] is None or t['stop_id']==update['stop_id']) and (update['stop_sequence'] is None or t['sequence']==update['stop_sequence'])]
  if (not update['stop_id'] and update['stop_sequence'] is None) or len(matches)!=1:flags.append('Ambiguous or mismatched stop-time update');continue
  sequence=matches[0]['sequence']
  if sequence in seen:flags.append('Duplicate stop-time update')
  seen.add(sequence)
  if update['arrival_time'] is not None and not 0<=update['arrival_time']<=253402300799:flags.append('Invalid arrival timestamp')
  if update['relationship']==gtfs.TripUpdate.StopTimeUpdate.NO_DATA and (update['arrival_time'] is not None or update['delay'] is not None):flags.append('NO_DATA must not contain predicted timing')
 if progress is None and record.get('stop_sequence'):
  progress=next((i for i,t in enumerate(info['times']) if t['sequence']==record['stop_sequence']),None)
 if previous and record['kind']=='vehicle_position':
  prior=instant(previous['observed_at']);delta=(observed-prior).total_seconds()
  if delta<=0:flags.append('Duplicate or out-of-order vehicle update')
  if lat is not None and lon is not None and previous.get('latitude') is not None and delta>0:
   if distance((lat,lon),(previous['latitude'],previous['longitude']))/delta>45:flags.append('Impossible speed or abrupt jump')
  if previous.get('trip_id')==record['trip_id'] and previous.get('service_date')==record['service_date'] and progress is not None and previous.get('progress') is not None and progress<previous['progress']-.4:flags.append('Stop progression moved backward')
 if flags:status='rejected'
 elif age>120:status='stale'
 elif record.get('cancelled'):status='cancelled'
 return {**record,'source_id':source,'observed_at':observed.isoformat(),'ingested_at':store.stamp(),'progress':progress,'logical_route':logical_route(info),'status':status,'flags':flags}

def ingest(raw,*,sid,provenance,license_name,source_mode='replay',synthetic=False,path=None):
 if source_mode=='authorized' and (synthetic or os.getenv('TRANSIT_FEED_AUTHORIZED','false').lower()!='true'):raise ValueError('Authorized ingestion requires explicit provider permission; fixtures cannot be live')
 if source_mode not in ['replay','authorized']:raise ValueError('Feed mode must be replay or authorized')
 if not sid or len(sid)>80 or not provenance.strip() or not license_name.strip():raise ValueError('Source ID, provenance and license are required')
 try:header,records=parse_feed(raw)
 except ValueError:
  with store.connect() as db:
   db.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?,?,?)',(sid,source_mode,provenance,license_name,int(synthetic),'error',None,'Invalid feed payload'))
   db.execute("UPDATE sources SET status='error',error='Invalid feed payload' WHERE id=?",(sid,))
   db.execute('INSERT OR IGNORE INTO raw_feeds VALUES (?,?,?,?,?)',(hashlib.sha256(sid.encode()+raw).hexdigest(),sid,store.stamp(),raw if len(raw)<=5_000_000 else b'','rejected'))
  raise
 clock=datetime.fromtimestamp(header,timezone.utc) if source_mode=='replay' else store.now()
 raw_id=hashlib.sha256(sid.encode()+raw).hexdigest();result=dict(accepted=0,rejected=0,unmatched=0,stale=0,informational=0,cancelled=0,duplicates=0)
 with store.connect() as db:
  latest=db.execute('SELECT feed_timestamp FROM source_snapshots WHERE source_id=?',(sid,)).fetchone()
  if latest and header<latest['feed_timestamp']:raise ValueError('Out-of-order full feed snapshot')
  existing=db.execute('SELECT mode,synthetic FROM sources WHERE id=?',(sid,)).fetchone()
  if existing and (existing['mode']!=source_mode or bool(existing['synthetic'])!=synthetic):raise ValueError('Source mode/provenance cannot be silently relabeled; choose a new source ID')
  db.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?,?,?)',(sid,source_mode,provenance,license_name,int(synthetic),'configured',None,None))
  if db.execute('SELECT id FROM raw_feeds WHERE id=?',(raw_id,)).fetchone():return {**result,'duplicates':len(records)}
  db.execute('INSERT INTO raw_feeds VALUES (?,?,?,?,?)',(raw_id,sid,store.stamp(),raw,'parsed'))
  snapshot_ids=[]
  for record in records:
   previous=None
   if record.get('vehicle_id'):
    previous_row=db.execute("SELECT payload FROM transport_observations WHERE source_id=? AND vehicle_id=? AND kind=? AND status IN ('accepted','stale') ORDER BY observed_at DESC LIMIT 1",(sid,record['vehicle_id'],record['kind'])).fetchone()
    if previous_row:previous=json.loads(previous_row['payload'])
   unchanged=previous and all(previous.get(k)==v for k,v in record.items() if k!='feed_timestamp')
   normalized=normalize(record,sid,clock,path,None if unchanged else previous)
   if normalized['status']=='accepted' and record['kind']=='vehicle_position':
    others=db.execute("SELECT vehicle_id,observed_at FROM transport_observations WHERE source_id=? AND trip_id=? AND service_date=? AND kind='vehicle_position' AND status='accepted'",(sid,record['trip_id'],record['service_date'])).fetchall()
    if any(r['vehicle_id']!=record['vehicle_id'] and abs((instant(normalized['observed_at'])-instant(r['observed_at'])).total_seconds())<120 for r in others):
     normalized['status']='rejected';normalized['flags'].append('Multiple vehicles claim one scheduled trip instance')
   if normalized.get('logical_route',{}).get('synthetic') and not synthetic:
    normalized['status']='rejected';normalized['flags'].append('Synthetic registry cannot be used as a genuine source')
   ident=hashlib.sha256((raw_id+record['entity_id']+record['kind']).encode()).hexdigest();snapshot_ids.append(ident)
   if db.execute('SELECT id FROM transport_observations WHERE id=?',(ident,)).fetchone():result['duplicates']+=1;continue
   result[normalized['status']]+=1
   db.execute('INSERT INTO transport_observations VALUES (?,?,?,?,?,?,?,?,?)',(ident,sid,record.get('vehicle_id'),record.get('trip_id'),record.get('service_date'),normalized.get('observed_at'),record['kind'],normalized['status'],store.json_value(normalized)))
  db.execute('UPDATE sources SET status=?,last_success=?,error=NULL WHERE id=?',('ingested' if result['accepted'] else 'degraded',store.stamp(),sid))
  db.execute('INSERT OR REPLACE INTO source_snapshots VALUES (?,?,?)',(sid,header,store.json_value(snapshot_ids)))
 return result

def safe_url(url,allowed_hosts):
 parsed=urlsplit(url)
 if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in [None,443] or parsed.hostname not in allowed_hosts:raise ValueError('Feed must use HTTPS on an explicitly approved provider hostname')
 for item in socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM):
  if not ipaddress.ip_address(item[4][0]).is_global:raise ValueError('Provider hostname resolves to a non-public address')
 return url
def fetch_configured():
 if os.getenv('TRANSIT_FEED_AUTHORIZED','false').lower()!='true':raise ValueError('Provider permission must be explicitly confirmed in backend configuration')
 sid=source_id()
 if not sid or not os.getenv('TRANSIT_FEED_PROVENANCE') or not os.getenv('TRANSIT_FEED_LICENSE'):raise ValueError('Source ID, provider provenance and license must be configured before fetching')
 url=os.getenv('TRANSIT_FEED_URL','');hosts={h.strip() for h in os.getenv('TRANSIT_FEED_ALLOWED_HOSTS','').split(',') if h.strip()}
 safe_url(url,hosts)
 with store.connect() as db:
  row=db.execute('SELECT last_attempt FROM provider_attempts WHERE source_id=?',(sid,)).fetchone()
  if row and (store.now()-instant(row['last_attempt'])).total_seconds()<max(15,int(os.getenv('TRANSIT_POLL_SECONDS','60'))):raise ValueError('Provider polling interval has not elapsed')
  db.execute('INSERT OR REPLACE INTO provider_attempts VALUES (?,?)',(sid,store.stamp()))
  db.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?,?,?)',(sid,'authorized',os.getenv('TRANSIT_FEED_PROVENANCE'),os.getenv('TRANSIT_FEED_LICENSE'),0,'configured',None,None))
 try:
  headers={'Authorization':'Bearer '+os.environ['TRANSIT_FEED_TOKEN']} if os.getenv('TRANSIT_FEED_TOKEN') else {}
  with httpx.Client(timeout=15,follow_redirects=False,trust_env=False) as client:
   with client.stream('GET',url,headers=headers) as response:
    if response.status_code!=200:raise ValueError('Provider returned a non-success response; no credentials or response content exposed')
    chunks=[];size=0
    for chunk in response.iter_bytes():
     size+=len(chunk)
     if size>5_000_000:raise ValueError('Feed exceeds size limit')
     chunks.append(chunk)
  return ingest(b''.join(chunks),sid=sid,provenance=os.getenv('TRANSIT_FEED_PROVENANCE',''),license_name=os.getenv('TRANSIT_FEED_LICENSE',''),source_mode='authorized')
 except Exception:
  with store.connect() as db:db.execute("UPDATE sources SET status='error',error='Provider fetch failed; check local configuration and provider access' WHERE id=?",(sid,))
  raise ValueError('Provider fetch failed; no external connection verified') from None

def current_records():
 with store.connect() as db:
  source=db.execute('SELECT * FROM sources WHERE id=?',(source_id(),)).fetchone()
  snapshot=db.execute('SELECT observation_ids,feed_timestamp FROM source_snapshots WHERE source_id=?',(source_id(),)).fetchone()
  ids=json.loads(snapshot['observation_ids']) if snapshot else []
  rows=[]
  for offset in range(0,len(ids),400):
   batch=ids[offset:offset+400]
   rows+=db.execute("SELECT payload FROM transport_observations WHERE source_id=? AND id IN ("+','.join('?' for _ in batch)+") AND status IN ('accepted','stale','cancelled','informational') ORDER BY observed_at DESC",[source_id(),*batch]).fetchall()
 if not source or mode()=='schedule' or source['mode']!=mode() or (source['synthetic'] and os.getenv('RUSHLESS_TEST_MODE')!='true'):return None,[]
 unique={}
 for row in rows:
  p=json.loads(row[0]);key=(p['entity_id'] if p['kind']=='service_alert' else (p.get('vehicle_id') or p['trip_id'],p.get('service_date')),p['kind']);unique.setdefault(key,p)
 return {**dict(source),'feed_timestamp':snapshot['feed_timestamp'] if snapshot else None},list(unique.values())
def external_snapshot():
 if mode()!='schedule':return build_external_snapshot()
 path=registry_path();key=(str(path),path.stat().st_mtime_ns if path.exists() else 0)
 with PREVIEW_LOCK:
  cached=PREVIEW_CACHE.get(key)
  if cached and time.monotonic()-cached[0]<10:return cached[1]
  value=build_external_snapshot();PREVIEW_CACHE.clear();PREVIEW_CACHE[key]=(time.monotonic(),value);return value

def build_external_snapshot():
 source,records=current_records();clock=store.now()
 if mode()=='replay' and source and source.get('feed_timestamp') is not None:clock=datetime.fromtimestamp(source['feed_timestamp'],timezone.utc)
 vehicles=[]
 for p in records:
  if p['kind'] not in ['vehicle_position','trip_update']:continue
  if p['kind']=='trip_update' and any(r['kind']=='vehicle_position' and r['trip_id']==p['trip_id'] and r['service_date']==p['service_date'] for r in records):continue
  info=trip_info(p['trip_id'])
  if not info:continue
  update=next((r for r in records if r['kind']=='trip_update' and r['trip_id']==p['trip_id'] and r['service_date']==p['service_date'] and (not r.get('vehicle_id') or not p.get('vehicle_id') or r['vehicle_id']==p['vehicle_id'])),None)
  age=max(0,(clock-instant(p['observed_at'])).total_seconds());source_mode='replay_synthetic' if source['synthetic'] else 'historical_replay' if mode()=='replay' else 'real_observed'
  latest=next((t['id'] for t in info['times'] if t['stop_id']==p.get('stop_id')),None)
  vehicles.append(dict(id=p.get('vehicle_id') or 'trip-update:'+p['trip_id'],trip_id=p['trip_id'],route_id=p['logical_route']['id'],route_name=p['logical_route']['name'],lat=p.get('latitude'),lon=p.get('longitude'),next_stop=latest or info['times'][min(len(info['times'])-1,max(0,math.ceil(p.get('progress') or 0)))]['id'],passengers=None,capacity=None,source=source_mode,external=True,record=p,update=update,service_date=p['service_date'],completed=p['status']=='cancelled' or bool(update and update['status']=='cancelled'),progress=p.get('progress'),segment_seconds=180,metadata=dict(source=source_mode,method='provider_trip_update' if update else 'vehicle_progress',confidence='Low' if age>120 else 'Medium',observed_at=p['observed_at'],generated_at=clock.isoformat(),reason='Provider/replay evidence; not a guarantee of accuracy',generation=source['id']+':'+p['service_date'],evidence='Provider occupancy status, if supplied; no GPS-derived counts',uncertainty=None,observation_age_seconds=age)))
 vehicles+=scheduled_vehicles(clock,{(v['trip_id'],v['service_date']) for v in vehicles})
 return 0,clock,vehicles

def scheduled_vehicles(clock,excluded,target=None,destination=None):
 path=registry_path()
 if not path.exists():return []
 vehicles=[]
 from .network import status as network_status
 imported_at=network_status().get('imported_at',(clock-timedelta(hours=1)).isoformat())
 from .schedule import service_active
 from .main import STOPS
 ids=[s.get('gtfs_stop_id',s['id']) for s in STOPS]
 try:
  with closing(sqlite3.connect(path)) as db:
   local=clock.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata'));sec=local.hour*3600+local.minute*60+local.second
   if db.execute("SELECT 1 FROM sqlite_master WHERE name='network_metadata'").fetchone():
    clause=' AND s.stop_id=?' if target else ''
    args=[sec,sec+7200,sec+86400,sec+86400+7200]+([original(target)] if target else [])
    rows=db.execute('SELECT DISTINCT s.trip_id FROM stop_times s WHERE ((s.arrival_seconds BETWEEN ? AND ?) OR (s.arrival_seconds BETWEEN ? AND ?))'+clause+' ORDER BY s.arrival_seconds LIMIT 200',args).fetchall()
   else:rows=db.execute('SELECT DISTINCT trip_id FROM stop_times WHERE stop_id IN ('+','.join('?' for _ in ids)+') LIMIT 500',ids).fetchall()
   for (tid,) in rows:
    info=trip_info(tid)
    if not info:continue
    if destination and destination not in [t['id'] for t in info['times']]:continue
    for offset in [0,-1]:
     local=clock.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata'))+timedelta(days=offset);date=local.strftime('%Y%m%d')
     if (tid,date) in excluded or not service_active(db,info['trip']['service_id'],local):continue
     future=[t for t in info['times'] if service_stamp(date,t['seconds'])>clock]
     if not future or (service_stamp(date,future[0]['seconds'])-clock).total_seconds()>7200:continue
     route=logical_route(info);record=dict(trip_id=tid,service_date=date,observed_at=imported_at,progress=None,logical_route=route,updates=[],occupancy_status=None)
     vehicles.append(dict(id='scheduled:'+tid+':'+date,trip_id=tid,route_id=route['id'],route_name=route['name'],lat=None,lon=None,next_stop=future[0]['id'],passengers=None,capacity=None,source='schedule',external=True,record=record,update=None,service_date=date,completed=False,progress=None,segment_seconds=180,metadata=dict(source='schedule',method='scheduled_baseline',confidence='Low',observed_at=record['observed_at'],generated_at=clock.isoformat(),generation='schedule:'+date,evidence='GTFS schedule only; no observed vehicle position',reason='No fresh observed vehicle information')))
 except sqlite3.Error:return []
 return vehicles

def scheduled_trip_vehicle(trip_id,service_date,clock,*,service_verified=False,imported_at=None):
 """Resolve a watched instance even outside the bounded network preview."""
 if not service_date:return None
 info=trip_info(trip_id)
 if not info:return None
 from .schedule import service_active
 try:
  day=datetime.strptime(service_date,'%Y%m%d')
  if not service_verified:
   with closing(sqlite3.connect(registry_path())) as db:
    if not service_active(db,info['trip']['service_id'],day):return None
 except (ValueError,sqlite3.Error):return None
 route=logical_route(info)
 from .network import status as network_status
 stamp=imported_at or network_status().get('imported_at',clock.isoformat())
 record=dict(trip_id=trip_id,service_date=service_date,observed_at=stamp,progress=None,logical_route=route,updates=[],occupancy_status=None)
 return dict(id='scheduled:'+trip_id+':'+service_date,trip_id=trip_id,route_id=route['id'],route_name=route['name'],lat=None,lon=None,next_stop=None,external=True,record=record,update=None,service_date=service_date,completed=False,progress=None,metadata=dict(source='schedule',method='scheduled_baseline',confidence='Low',observed_at=stamp,generated_at=clock.isoformat(),generation='schedule:'+service_date,reason='Published timetable only; no fresh observed vehicle',evidence='GTFS schedule only'))

def get_external_route(rid):
 if rid in ROUTE_CACHE:return ROUTE_CACHE[rid]
 from .network import pattern
 found=pattern(rid)
 if found:return found
 _,records=current_records()
 return next((r['logical_route'] for r in records if r.get('logical_route',{}).get('id')==rid),None)
def external_routes(q='',limit=200):
 from .network import patterns,status
 static=patterns(q,limit)
 if static or status().get('validation')!='not_imported':return static
 _,_,vehicles=external_snapshot()
 return [r for r in {v['route_id']:get_external_route(v['route_id']) for v in vehicles}.values() if r and q.casefold() in r['name'].casefold()][:limit]
def external_prediction(v,target,elapsed,clock,*,target_index=None):
 from .main import Metadata
 from .predictive import uncertainty
 info=trip_info(v['trip_id']);times=info['times'];index=target_index if target_index is not None else next((i for i,t in enumerate(times) if t['id']==target),None)
 if index is not None and (not 0<=index<len(times) or times[index]['id']!=target):return None
 if index is None:return None
 p=v['record'];age=max(0,(clock-instant(p['observed_at'])).total_seconds());scheduled=service_stamp(v['service_date'],times[index]['seconds']);estimate=scheduled;method='scheduled_baseline';progress=p.get('progress')
 if progress is not None and age<=120 and index<progress-.05:return None
 update=v.get('update');update_age=(clock-instant(update['observed_at'])).total_seconds() if update else float('inf')
 no_data=False
 if update and update_age<=120:
  if update.get('cancelled'):return None
  indexed=[]
  for u in update['updates']:
   at=next((i for i,t in enumerate(times) if (u['stop_sequence']==t['sequence'] if u['stop_sequence'] is not None else u['stop_id']==t['stop_id'])),None)
   if at is not None and at<=index:indexed.append((at,u))
  relevant=next((u for i,u in indexed if i==index),None)
  if relevant and relevant['relationship']==gtfs.TripUpdate.StopTimeUpdate.SKIPPED:return None
  prior=sorted([(i,u) for i,u in indexed if u['relationship']!=gtfs.TripUpdate.StopTimeUpdate.SKIPPED],key=lambda pair:pair[0])
  upstream=prior[-1] if prior else None
  no_data=bool(upstream and upstream[1]['relationship']==gtfs.TripUpdate.StopTimeUpdate.NO_DATA)
  if no_data:relevant=None
  if relevant and relevant['arrival_time'] is not None:estimate=datetime.fromtimestamp(relevant['arrival_time'],timezone.utc);method='provider_trip_update'
  elif relevant and relevant['delay'] is not None:estimate=scheduled+timedelta(seconds=relevant['delay']);method='provider_delay'
  elif upstream and not no_data:
   i,u=upstream
   delay=(u['arrival_time']-service_stamp(v['service_date'],times[i]['seconds']).timestamp()) if u['arrival_time'] is not None else u['delay']
   if delay is not None:estimate=scheduled+timedelta(seconds=delay);method='provider_delay'
  elif not no_data and update.get('delay') is not None:estimate=scheduled+timedelta(seconds=update['delay']);method='provider_delay'
 if method=='scheduled_baseline' and not no_data and age<=120 and progress is not None:
  segment=min(len(times)-2,max(0,math.floor(progress)));fraction=progress-segment
  at_seconds=times[segment]['seconds']+(times[segment+1]['seconds']-times[segment]['seconds'])*fraction
  estimate=instant(p['observed_at'])+timedelta(seconds=times[index]['seconds']-at_seconds);method='vehicle_progress'
 remaining=(estimate-clock).total_seconds()
 if remaining<=0:return None
 category={gtfs.VehiclePosition.EMPTY:'Low',gtfs.VehiclePosition.MANY_SEATS_AVAILABLE:'Low',gtfs.VehiclePosition.FEW_SEATS_AVAILABLE:'Moderate',gtfs.VehiclePosition.STANDING_ROOM_ONLY:'Moderate',gtfs.VehiclePosition.CRUSHED_STANDING_ROOM_ONLY:'High',gtfs.VehiclePosition.FULL:'High',gtfs.VehiclePosition.NOT_ACCEPTING_PASSENGERS:'High'}.get(p.get('occupancy_status'),'Unknown') if age<=120 else 'Unknown'
 # Current qualitative occupancy is not a future count model. Show Unknown beyond current stop.
 current_category=category
 category='Unknown'  # No per-stop forward boarding/alighting evidence is supplied by this adapter.
 bounds=uncertainty(remaining,max(0,index-(progress or 0)),age,'normal');bounds['label']='Heuristic range from source age and stop horizon; not calibrated';bounds['occupancy_uncertainty']='High'
 source=v['metadata']['source'] if method!='scheduled_baseline' else 'schedule'
 metadata={**v['metadata'],'source':source,'method':method,'uncertainty':bounds,'confidence':'Low' if method=='scheduled_baseline' or age>120 else 'Medium','source_id':source_id(),'current_crowding':current_category,'evidence':'Current provider status is separate from future occupancy; forward crowding unknown without evidence'}
 if source=='real_observed':
  from .ground_truth import calibrated_bounds
  bounds=calibrated_bounds(method,v['route_id'],remaining,bounds);metadata['uncertainty']=bounds
 result=dict(segment_index=math.floor(progress) if progress is not None else None,stops_remaining=index-math.floor(progress) if progress is not None else None,vehicle_id=v['id'],trip_id=v['trip_id'],route_id=v['route_id'],route_name=v['route_name'],target_stop=target,minutes=round(remaining/60,1),arrival_at=estimate.isoformat(),scheduled_at=scheduled.isoformat(),delay_minutes=round((estimate-scheduled).total_seconds()/60,1),crowding=category,utilization=None,metadata=metadata,uncertainty=bounds)
 if source=='real_observed':
  from .ground_truth import record_forecast
  record_forecast(result,v['service_date'])
 return result

def health():
 with store.connect() as db:
  sources=[dict(r) for r in db.execute('SELECT * FROM sources')];counts=[dict(r) for r in db.execute('SELECT source_id,status,COUNT(*) AS n FROM transport_observations GROUP BY source_id,status')]
  verified=db.execute("SELECT COUNT(*) FROM pilot_observations WHERE status='verified' AND source_type='real_observed'").fetchone()[0]
 for source in sources:
  with store.connect() as db:
   latest=db.execute("SELECT MAX(observed_at) FROM transport_observations WHERE source_id=? AND status='accepted'",(source['id'],)).fetchone()[0]
   details=[json.loads(r[0]) for r in db.execute('SELECT payload FROM transport_observations WHERE source_id=?',(source['id'],))]
  source['invalid_geographic_positions']=sum(any('geographic' in flag or 'geometry' in flag for flag in record.get('flags',[])) for record in details)
  source['route_coverage']=sorted({record['logical_route']['id'] for record in details if record.get('logical_route') and record['status']=='accepted'})
  source['latest_observation_at']=latest;source['observation_age_seconds']=max(0,(store.now()-instant(latest)).total_seconds()) if latest else None
  source['counts']={r['status']:r['n'] for r in counts if r['source_id']==source['id']}
  source['live_verified']=source['mode']=='authorized' and not source['synthetic'] and source['status']=='ingested' and source['observation_age_seconds'] is not None and source['observation_age_seconds']<=120
 connected=mode()=='authorized' and any(s['live_verified'] and s['id']==source_id() for s in sources)
 from .main import ROUTES,STOPS
 from .history import dataset_summary
 datasets=dataset_summary()['datasets']
 return dict(serving_scope=dict(routes=len(ROUTES) if mode()=='simulation' else len(external_routes()),stops=len(STOPS)),historical_coverage=dict(declared_simulation_rows=sum(d['count'] for d in datasets if d['mode']=='simulation' and d['status']=='ready'),declared_observed_rows=sum(d['count'] for d in datasets if d['mode']=='real_observed' and d['status']=='ready'),note='CSV source declarations are not independent verification.'),mode=mode(),live_connected=connected,message='Authorized transport feed verified recently.' if connected else 'BMTC live tracking is not connected.',sources=sources,verified_labels=verified,calibration_available=False,note='Replay and synthetic fixtures are never marked as live. Counts cover this configured corridor only.')

def fixture(directory):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 from .main import STOPS
 dbpath=directory/'fixture-gtfs.db';feed=gtfs.FeedMessage();clock=store.now();feed.header.gtfs_realtime_version='2.0';feed.header.timestamp=int(clock.timestamp())
 with closing(sqlite3.connect(dbpath)) as db:
  db.executescript('CREATE TABLE IF NOT EXISTS routes(route_id TEXT,route_short_name TEXT);CREATE TABLE IF NOT EXISTS trips(trip_id TEXT,route_id TEXT,service_id TEXT,direction_id TEXT);CREATE TABLE IF NOT EXISTS stops(stop_id TEXT,stop_name TEXT,stop_lat REAL,stop_lon REAL);CREATE TABLE IF NOT EXISTS stop_times(trip_id TEXT,stop_id TEXT,stop_sequence INTEGER,arrival_time TEXT);CREATE TABLE IF NOT EXISTS calendar_dates(service_id TEXT,date TEXT,exception_type TEXT);')
  for table in ['routes','trips','stops','stop_times','calendar_dates']:db.execute('DELETE FROM '+table)
  db.execute('CREATE TABLE IF NOT EXISTS rushless_registry_metadata(synthetic INTEGER)');db.execute('DELETE FROM rushless_registry_metadata');db.execute('INSERT INTO rushless_registry_metadata VALUES (1)')
  db.execute("INSERT INTO routes VALUES ('fixture-route','FIXTURE')");db.execute("INSERT INTO trips VALUES ('fixture-trip','fixture-route','fixture-service','0')")
  day=clock.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata'));db.execute('INSERT INTO calendar_dates VALUES (?,?,?)',('fixture-service',day.strftime('%Y%m%d'),'1'))
  seconds=day.hour*3600+day.minute*60+day.second
  for i,s in enumerate(STOPS):
   db.execute('INSERT INTO stops VALUES (?,?,?,?)',(s['id'],s['name'],s['lat'],s['lon']));t=seconds+(i-1)*180
   db.execute('INSERT INTO stop_times VALUES (?,?,?,?)',('fixture-trip',s['id'],i+1,f'{t//3600:02}:{t%3600//60:02}:{t%60:02}'))
  db.commit()
 entity=feed.entity.add();entity.id='fixture-position';v=entity.vehicle;v.trip.trip_id='fixture-trip';v.trip.route_id='fixture-route';v.trip.direction_id=0;v.trip.start_date=day.strftime('%Y%m%d');v.vehicle.id='FIXTURE-BUS';v.timestamp=int(clock.timestamp());v.position.latitude=STOPS[1]['lat'];v.position.longitude=STOPS[1]['lon'];v.stop_id=STOPS[1]['id'];v.current_stop_sequence=2;v.occupancy_status=gtfs.VehiclePosition.MANY_SEATS_AVAILABLE
 entity=feed.entity.add();entity.id='fixture-update';u=entity.trip_update;u.trip.CopyFrom(v.trip);u.vehicle.id=v.vehicle.id;u.timestamp=v.timestamp;update=u.stop_time_update.add();update.stop_id=STOPS[-1]['id'];update.arrival.time=int(clock.timestamp())+(len(STOPS)-2)*180+60
 file=directory/'synthetic-replay.pb';file.write_bytes(feed.SerializeToString());return dbpath,file

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
 f=sub.add_parser('fixture');f.add_argument('--directory',default=str(ROOT/'data/feed-fixtures'))
 imp=sub.add_parser('ingest');imp.add_argument('file');imp.add_argument('--source-id',required=True);imp.add_argument('--provenance',required=True);imp.add_argument('--license',required=True);imp.add_argument('--synthetic',action='store_true')
 sub.add_parser('fetch');args=parser.parse_args()
 try:
  if args.command=='fixture':print('\n'.join(str(p) for p in fixture(args.directory)))
  elif args.command=='fetch':print(json.dumps(fetch_configured()))
  else:print(json.dumps(ingest(Path(args.file).read_bytes(),sid=args.source_id,provenance=args.provenance,license_name=args.license,synthetic=args.synthetic)))
 except (ValueError,sqlite3.Error) as exc:parser.exit(2,str(exc)+'\n')
