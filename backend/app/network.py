"""Versioned published GTFS network. Local administrative import only."""
import argparse, hashlib, json, os, sqlite3, zipfile, uuid
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from contextlib import closing
from functools import lru_cache
import threading
PATTERN_LOCK=threading.RLock()
from .import_gtfs import seconds
ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'data/network-active.json'
SOURCE='https://github.com/Vonter/bmtc-gtfs'
def active_path():
 if os.getenv('GTFS_DB_PATH'):return Path(os.environ['GTFS_DB_PATH'])
 if MANIFEST.exists():return Path(json.loads(MANIFEST.read_text())['path'])
 return ROOT/'data/gtfs.db'
def connect():
 db=sqlite3.connect('file:'+active_path().as_posix()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
def import_network(archive, directory, activate=False):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 digest=hashlib.sha256(Path(archive).read_bytes()).hexdigest();output=directory/(digest[:16]+'.db')
 if output.exists():raise ValueError('Version already imported; previous version preserved')
 temp=output.with_suffix('.'+uuid.uuid4().hex+'.pending');report={'sha256':digest,'source':SOURCE,'license':'ODbL-1.0; BMTC underlying content copyright retained','imported_at':datetime.now(timezone.utc).isoformat(),'warnings':['Unofficial dataset; upstream warns of incorrect timetables and missing routes.'],'rejected_trips':0}
 try:
  with zipfile.ZipFile(archive) as z,sqlite3.connect(temp) as db:
   frames={name:pd.read_csv(z.open(name+'.txt'),dtype=str,keep_default_na=False) for name in ['stops','routes','trips','stop_times']}
   if not ({'calendar.txt','calendar_dates.txt'} & set(z.namelist())):raise ValueError('Service calendar is required')
   for name,key in [('stops','stop_id'),('routes','route_id'),('trips','trip_id')]:
    if frames[name][key].duplicated().any():raise ValueError('Duplicate '+key)
   stops=frames['stops'];lat=pd.to_numeric(stops.stop_lat,errors='coerce');lon=pd.to_numeric(stops.stop_lon,errors='coerce')
   valid=lat.between(12,14)&lon.between(77,78.5);report['rejected_stops']=int((~valid).sum());frames['stops']=stops[valid]
   trips=frames['trips'];times=frames['stop_times']
   def parse(t):
    try:return seconds(t)
    except (ValueError,TypeError):return None
   times['arrival_seconds']=times.arrival_time.map(parse);times['departure_seconds']=times.departure_time.map(parse);times['seq']=pd.to_numeric(times.stop_sequence,errors='coerce')
   invalid=times.arrival_seconds.isna()|times.departure_seconds.isna()|times.seq.isna()|~times.stop_id.isin(frames['stops'].stop_id)|(times.departure_seconds<times.arrival_seconds)|times.duplicated(['trip_id','stop_sequence'],keep=False)
   bad=set(times[invalid].trip_id);ordered=times.sort_values(['trip_id','seq']);back=(ordered.arrival_seconds<ordered.groupby('trip_id').departure_seconds.shift());bad.update(ordered[back].trip_id)
   bad.update(times.groupby('trip_id').size().loc[lambda s:s<2].index)
   trips=trips[trips.route_id.isin(frames['routes'].route_id)&~trips.trip_id.isin(bad)]
   report['rejected_trips']=len(frames['trips'])-len(trips);frames['trips']=trips;times=ordered[ordered.trip_id.isin(trips.trip_id)];frames['stop_times']=times
   if trips.empty:raise ValueError('No valid trips')
   for name,frame in frames.items():frame.to_sql(name,db,index=False)
   for name in ['agency','calendar','calendar_dates','feed_info','attributions','fare_attributes','fare_rules','transfers']:
    if name+'.txt' in z.namelist():pd.read_csv(z.open(name+'.txt'),dtype=str,keep_default_na=False).to_sql(name,db,index=False)
   bad_shapes=set()
   if 'shapes.txt' in z.namelist():
    for chunk in pd.read_csv(z.open('shapes.txt'),dtype=str,keep_default_na=False,chunksize=100000):
     a=pd.to_numeric(chunk.shape_pt_lat,errors='coerce');b=pd.to_numeric(chunk.shape_pt_lon,errors='coerce')
     valid_shape=a.between(12,14)&b.between(77,78.5)
     bad_shapes.update(chunk.loc[~valid_shape,'shape_id'])
     chunk.to_sql('shapes',db,index=False,if_exists='append')
    db.execute('CREATE INDEX shape_lookup ON shapes(shape_id)')
    db.executemany('DELETE FROM shapes WHERE shape_id=?',[(sid,) for sid in bad_shapes])
   report['quarantined_shapes']=len(bad_shapes)
   patterns=[];mapping=[];seen=set();tripmap=trips.set_index('trip_id').to_dict('index')
   for tid,group in times.groupby('trip_id',sort=False):
    trip=tripmap[tid];signature=hashlib.sha256((','.join(group.stop_id)+':'+trip.get('shape_id','')).encode()).hexdigest()[:16]
    rid='gtfs:'+trip['route_id']+':'+str(trip.get('direction_id',''))+':'+signature
    mapping.append((tid,rid))
    if rid not in seen:patterns.append((rid,tid,trip['route_id'],str(trip.get('direction_id',''))));seen.add(rid)
   db.execute('CREATE TABLE network_patterns(id TEXT PRIMARY KEY,trip_id TEXT,route_id TEXT,direction TEXT)');db.executemany('INSERT INTO network_patterns VALUES (?,?,?,?)',patterns)
   db.execute('CREATE TABLE trip_patterns(trip_id TEXT PRIMARY KEY,pattern_id TEXT)');db.executemany('INSERT INTO trip_patterns VALUES (?,?)',mapping)
   for sql in ['CREATE INDEX trip_lookup ON trips(trip_id)','CREATE INDEX time_lookup ON stop_times(trip_id,stop_id)','CREATE INDEX stop_lookup ON stop_times(stop_id,arrival_seconds)','CREATE INDEX route_lookup ON routes(route_id)','CREATE INDEX stops_id_lookup ON stops(stop_id)','CREATE INDEX time_clock_lookup ON stop_times(arrival_seconds,trip_id)']:db.execute(sql)
   report.update(routes=len(frames['routes']),stops=len(frames['stops']),trips=len(trips),patterns=len(patterns),stop_times=len(times),validation='passed_with_upstream_caveats')
   report['feed_info']=[]
   if 'feed_info.txt' in z.namelist():report['feed_info']=pd.read_csv(z.open('feed_info.txt'),dtype=str,keep_default_na=False).to_dict('records')
   db.execute('CREATE TABLE network_metadata(payload TEXT)');db.execute('INSERT INTO network_metadata VALUES (?)',(json.dumps(report),))
   db.execute('CREATE TABLE rushless_registry_metadata(synthetic INTEGER)');db.execute('INSERT INTO rushless_registry_metadata VALUES (0)')
  db.close()
  os.replace(temp,output);output.with_suffix('.json').write_text(json.dumps(report,indent=2))
  if activate:
   pointer=MANIFEST.with_suffix('.pending');pointer.write_text(json.dumps({'path':str(output.resolve()),'sha256':digest}));os.replace(pointer,MANIFEST)
  return {**report,'path':str(output)}
 except Exception:
  if 'db' in locals():db.close()
  temp.unlink(missing_ok=True);raise

def status():
 try:
  with closing(connect()) as db:return json.loads(db.execute('SELECT payload FROM network_metadata').fetchone()[0])
 except (sqlite3.Error,OSError):return {'validation':'not_imported','routes':0,'stops':0,'trips':0}
def stops():
 with closing(connect()) as db:return [dict(id={'20707':'silk','22670':'marathahalli'}.get(r['stop_id'],r['stop_id']),gtfs_stop_id=r['stop_id'],name=r['stop_name'],lat=float(r['stop_lat']),lon=float(r['stop_lon']),context=(r['stop_desc'] if 'stop_desc' in r.keys() else '') or 'BMTC published stop') for r in db.execute('SELECT * FROM stops ORDER BY CASE WHEN stop_id IN (\'20707\',\'22670\') THEN 0 ELSE 1 END,stop_name')]
def patterns(q='',limit=200):
 path=active_path()
 if not path.exists():return []
 with PATTERN_LOCK:return cached_patterns(str(path),path.stat().st_mtime_ns,q,limit)

@lru_cache(maxsize=64)
def cached_patterns(path,mtime,q,limit):
 from .feeds import trip_info,logical_route
 try:
  with closing(connect()) as db:rows=db.execute("SELECT p.trip_id FROM network_patterns p JOIN routes r ON r.route_id=p.route_id WHERE r.route_short_name LIKE ? OR r.route_long_name LIKE ? OR REPLACE(REPLACE(r.route_short_name,'-',''),' ','') LIKE ? LIMIT ?",('%'+q+'%','%'+q+'%','%'+q.replace('-','').replace(' ','')+'%',limit)).fetchall()
  return [logical_route(i) for row in rows if (i:=trip_info(row[0]))]
 except sqlite3.Error:return []


def pattern(rid):
 from .feeds import trip_info,logical_route
 try:
  with closing(connect()) as db:row=db.execute('SELECT trip_id FROM network_patterns WHERE id=?',(rid,)).fetchone()
  return logical_route(trip_info(row[0])) if row else None
 except sqlite3.Error:return None
@lru_cache(maxsize=256)
def departure_rows(path,mtime,pattern_id,stop_index):
 # Resolve the small trip set first. A four-way stop_times join let SQLite
 # scan the whole city timetable for each monitor poll on the imported feed.
 with closing(connect()) as db:
  trips=db.execute('SELECT t.trip_id,t.service_id FROM trip_patterns p JOIN trips t ON t.trip_id=p.trip_id WHERE p.pattern_id=?',(pattern_id,)).fetchall()
  rows=[]
  for trip in trips:
   times=db.execute('SELECT departure_seconds,arrival_seconds FROM stop_times WHERE trip_id=? ORDER BY seq',(trip['trip_id'],)).fetchall()
   if not 0<=stop_index<len(times):continue
   rows.append(dict(trip_id=trip['trip_id'],service_id=trip['service_id'],departure_seconds=times[0]['departure_seconds'],arrival_seconds=times[-1]['arrival_seconds'],stop_arrival_seconds=times[stop_index]['arrival_seconds'],stop_departure_seconds=times[stop_index]['departure_seconds']))
  return rows

def departures(pattern_id,clock,limit=5,stop_index=0):
 """Next published origin departures, including previous-day 24+ hour trips."""
 from .schedule import service_active,TZ
 from datetime import timedelta
 local=clock.astimezone(TZ)
 with closing(connect()) as db:
  if not db.execute('SELECT 1 FROM network_patterns WHERE id=?',(pattern_id,)).fetchone():return None
  path=active_path();rows=departure_rows(str(path.resolve()),path.stat().st_mtime_ns,pattern_id,stop_index)
  results=[]
  for offset in range(-1,8):
   day=(local+timedelta(days=offset)).replace(hour=0,minute=0,second=0,microsecond=0)
   for row in rows:
    departure=day+timedelta(seconds=row['departure_seconds']);arrival=day+timedelta(seconds=row['arrival_seconds'])
    at_stop=day+timedelta(seconds=row['stop_arrival_seconds']);leaving_stop=day+timedelta(seconds=row['stop_departure_seconds'])
    if leaving_stop<local or at_stop>local+timedelta(days=7) or not service_active(db,row['service_id'],day):continue
    results.append(dict(trip_id=row['trip_id'],service_date=day.strftime('%Y%m%d'),departure_at=departure.isoformat(),arrival_at=arrival.isoformat(),stop_arrival_at=at_stop.isoformat(),stop_departure_at=leaving_stop.isoformat(),source='schedule'))
  return sorted(results,key=lambda r:(r['stop_arrival_at'],r['trip_id']))[:limit]

def install_fares(archive):
 # Add published optional tables only when bytes exactly match this imported version.
 digest=hashlib.sha256(Path(archive).read_bytes()).hexdigest()
 if status().get('sha256')!=digest:raise ValueError('Archive hash does not match the active network')
 with zipfile.ZipFile(archive) as z,sqlite3.connect(active_path()) as db:
  for name in ['fare_attributes','fare_rules']:
   if db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(name,)).fetchone():continue
   frame=pd.read_csv(z.open(name+'.txt'),dtype=str,keep_default_na=False)
   if name=='fare_attributes':
    prices=pd.to_numeric(frame.price,errors='coerce')
    if not (prices.ge(0)&prices.le(10000)&frame.currency_type.eq('INR')).all():raise ValueError('Invalid published fare records')
   frame.to_sql(name,db,index=False)
  db.execute('CREATE INDEX IF NOT EXISTS fare_zone_lookup ON fare_rules(origin_id,destination_id,route_id)')
  db.execute('CREATE INDEX IF NOT EXISTS fare_id_lookup ON fare_attributes(fare_id)')

def fares(origin,destination):
 from .feeds import original
 result=[]
 try:
  with closing(connect()) as db:
   pair=[db.execute('SELECT zone_id FROM stops WHERE stop_id=?',(original(sid),)).fetchone() for sid in [origin,destination]]
   if not all(pair) or not all(row[0] for row in pair):return []
   patterns=db.execute('SELECT DISTINCT p.route_id,r.route_short_name FROM network_patterns p JOIN stop_times a ON a.trip_id=p.trip_id JOIN stop_times b ON b.trip_id=p.trip_id JOIN routes r ON r.route_id=p.route_id WHERE a.stop_id=? AND b.stop_id=? AND a.seq<b.seq',(original(origin),original(destination))).fetchall()
   for route in patterns:
    for fare in db.execute("SELECT DISTINCT f.fare_id,f.price,f.currency_type FROM fare_rules r JOIN fare_attributes f ON f.fare_id=r.fare_id WHERE r.origin_id=? AND r.destination_id=? AND (r.route_id='' OR r.route_id=?)",(pair[0][0],pair[1][0],route[0])):
     result.append(dict(route_id=route[0],route_name=route[1],fare_id=fare[0],amount=float(fare[1]),currency=fare[2]))
 except sqlite3.Error:return []
 return result

@lru_cache(maxsize=128)
def shape_points(path,mtime,shape_id):
 with closing(sqlite3.connect('file:'+Path(path).as_posix()+'?mode=ro',uri=True)) as db:
  return [[float(r[0]),float(r[1])] for r in db.execute('SELECT shape_pt_lat,shape_pt_lon FROM shapes WHERE shape_id=? ORDER BY CAST(shape_pt_sequence AS INTEGER)',(shape_id,))]

def geometry(tid, origin=None,destination=None):
 try:
  with closing(connect()) as db:
   t=db.execute('SELECT shape_id FROM trips WHERE trip_id=?',(tid,)).fetchone()
   path=active_path();points=shape_points(str(path.resolve()),path.stat().st_mtime_ns,t[0])
  if origin and destination and points:
   from .feeds import distance
   a=min(range(len(points)),key=lambda i:distance(points[i],[origin['lat'],origin['lon']]))
   b=min(range(a,len(points)),key=lambda i:distance(points[i],[destination['lat'],destination['lon']]))
   points=points[a:b+1]
  return points if len(points)>1 else []
 except (sqlite3.Error,TypeError):return []
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('zip');p.add_argument('--directory',default=str(ROOT/'data/network-versions'));p.add_argument('--activate',action='store_true');a=p.parse_args();print(json.dumps(import_network(a.zip,a.directory,a.activate),indent=2))
