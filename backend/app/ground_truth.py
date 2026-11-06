"""Pilot collection, explicit verification and forward-only real-world evaluation."""
import argparse
import csv
import hashlib
import json
import math
import os
import time
import uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field,AwareDatetime
from . import pilot_store as store
from .history import instant,metrics,occupancy_metrics

router=APIRouter(prefix='/api')
submission_limits={}
FORECAST_VERSION='phase4-observation-v1'
class PilotObservation(BaseModel):
 route_id:str=Field(max_length=100)
 stop_id:str=Field(max_length=100)
 direction:str=Field(max_length=100)
 service_date:str=Field(pattern=r'^\d{8}$')
 trip_id:str|None=Field(default=None,max_length=100)
 vehicle_id:str|None=Field(default=None,max_length=100)
 event_at:AwareDatetime
 method:Literal['volunteer_manual','authorized_arrival_record','authorized_passenger_count']='volunteer_manual'
 category:Literal['Low','Moderate','High']|None=None
 passenger_count:int|None=Field(default=None,ge=0,le=300)
 capacity:int|None=Field(default=None,ge=1,le=300)
 transport_source_id:str=Field(default='manual-pilot',max_length=80)
 note:str=Field(default='',max_length=200)

def catalog():
 from .main import ROUTES,STOPS
 from .feeds import trip_info,logical_route,registry_path
 real=[]
 path=registry_path()
 if path.exists():
  try:
   import sqlite3
   with sqlite3.connect('file:'+path.as_posix()+'?mode=ro',uri=True) as db:
    # Pick one candidate per route/direction; individual submitted trips are resolved exactly.
    trips=db.execute('SELECT MIN(trip_id) FROM trips GROUP BY route_id,direction_id LIMIT 100').fetchall()
   seed=Path(__file__).resolve().parents[2]/'data/corridor.json'
   if seed.exists():trips=[(json.loads(seed.read_text(encoding='utf-8'))['trip_reference'],)]+trips
   for (tid,) in trips:
    info=trip_info(tid)
    if info and logical_route(info)['id'] not in {r['id'] for r in real}:real.append(logical_route(info))
  except (ValueError,sqlite3.Error):pass
 return dict(routes=real+(ROUTES if os.getenv('RUSHLESS_TEST_MODE')=='true' else []),stops=STOPS,note='Only actual events should be submitted. Independent review is required for verification.')

def submit(body,kind,*,administrative=False,source_license=None):
 if kind not in ['arrival','occupancy']:raise HTTPException(422,'Unknown observation kind.')
 from .main import stop,crowd
 from .feeds import trip_info,logical_route
 options=catalog();route=next((r for r in options['routes'] if r['id']==body.route_id),None)
 if not route:raise HTTPException(422,'Route is not registered. Stage an authorized GTFS registry first.')
 stop(body.stop_id)
 if body.stop_id not in route['stops'] or body.direction!=route['direction']:raise HTTPException(422,'Route, direction and stop do not match.')
 delta=(store.now()-body.event_at.astimezone(timezone.utc)).total_seconds()
 if delta< -30 or (delta>7*86400 and not administrative):raise HTTPException(422,'Use an actual observation from the last seven days, not a prediction or a future time.')
 try:day=datetime.strptime(body.service_date,'%Y%m%d').date()
 except ValueError:raise HTTPException(422,'Invalid service date.')
 local=body.event_at.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata')).date()
 if not 0<=(local-day).days<=1:raise HTTPException(422,'Observation does not match its service instance.')
 if not administrative and body.method!='volunteer_manual':raise HTTPException(403,'Provider evidence must be imported through the local administrative workflow.')
 if (body.passenger_count is not None or body.capacity is not None) and not administrative:raise HTTPException(422,'Exact provider counts require an authorized local import; submit a category here.')
 if body.passenger_count is not None and (body.capacity is None or body.passenger_count>body.capacity):raise HTTPException(422,'Passenger count exceeds capacity or capacity is missing.')
 if kind=='occupancy' and body.category is None and body.passenger_count is None:raise HTTPException(422,'Select an observed crowd category.')
 synthetic=route.get('synthetic',False);matched=False
 if body.trip_id and not synthetic:
  info=trip_info(body.trip_id)
  if info and logical_route(info)['id']==route['id']:
   if body.stop_id not in [t['id'] for t in info['times']]:raise HTTPException(422,'That exact trip does not serve the selected stop.')
   from .schedule import service_active
   from .feeds import registry_path
   import sqlite3
   with sqlite3.connect(registry_path()) as db:matched=service_active(db,info['trip']['service_id'],datetime.combine(day,datetime.min.time()))
   if matched:
    from .schedule import scheduled_arrival
    from .feeds import original
    scheduled=scheduled_arrival(registry_path(),body.trip_id,next(t['stop_id'] for t in info['times'] if t['id']==body.stop_id),day.isoformat())
    if abs((body.event_at-scheduled).total_seconds())>10800:matched=False
 elif body.trip_id and synthetic:matched=body.trip_id.startswith(route['id']+'-trip-')
 status='matched' if matched else 'unresolved';source_type='simulation' if synthetic else 'real_observed'
 raw=body.model_dump(mode='json');normalized={**raw,'event_at':body.event_at.astimezone(timezone.utc).isoformat(),'kind':kind,'source_type':source_type,'matched':matched,'matching_method':'exact_trip_service_route_stop' if matched else 'unresolved','license':source_license}
 if body.passenger_count is not None:normalized['category']=crowd(body.passenger_count/body.capacity)
 fingerprint=hashlib.sha256(store.json_value([kind,body.transport_source_id,body.trip_id,body.route_id,body.stop_id,body.service_date,normalized['event_at'],normalized.get('category')]).encode()).hexdigest();ident=uuid.uuid4().hex
 with store.connect() as db:
  if db.execute('SELECT id FROM pilot_observations WHERE fingerprint=?',(fingerprint,)).fetchone():raise HTTPException(409,'This observation is already recorded.')
  if body.trip_id:
   others=db.execute("SELECT id,normalized,status FROM pilot_observations WHERE kind=? AND status IN ('matched','verified')",(kind,)).fetchall()
   for previous in others:
    p=json.loads(previous['normalized'])
    if all(p.get(k)==normalized.get(k) for k in ['transport_source_id','trip_id','stop_id','service_date']):
     gap=abs((instant(p['event_at'])-instant(normalized['event_at'])).total_seconds())
     if (kind=='arrival' and gap>30) or (kind=='occupancy' and gap<=120 and p.get('category')!=normalized.get('category')):
      status='unresolved';normalized['validation_note']='Conflicting observations require operator review.'
      if previous['status']!='verified':db.execute("UPDATE pilot_observations SET status='unresolved' WHERE id=?",(previous['id'],))
  db.execute('INSERT INTO pilot_observations VALUES (?,?,?,?,?,?,?,?,?,?)',(ident,fingerprint,kind,store.stamp(),normalized['event_at'],source_type,status,store.json_value(raw),store.json_value(normalized),None))
 return dict(id=ident,status=status,source_type=source_type,message='Recorded for review. Submission and trip matching do not independently verify an observation.')

def rate_limit(request):
 key=hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest();tick=time.monotonic()
 submission_limits[key]=[t for t in submission_limits.get(key,[]) if tick-t<3600]
 if len(submission_limits[key])>=20:raise HTTPException(429,'Pilot submission limit reached. Please return later.')
 submission_limits[key].append(tick)

@router.get('/observations/catalog')
def observation_catalog():return catalog()
@router.post('/observations/arrivals',status_code=201)
def arrival(body:PilotObservation,request:Request):rate_limit(request);return submit(body,'arrival')
@router.post('/observations/occupancy',status_code=201)
def occupancy(body:PilotObservation,request:Request):rate_limit(request);return submit(body,'occupancy')
@router.get('/observations/coverage')
def coverage():
 with store.connect() as db:
  counts=[dict(r) for r in db.execute('SELECT kind,source_type,status,COUNT(*) AS count FROM pilot_observations GROUP BY kind,source_type,status')]
 return dict(counts=counts,note='Submitted/matched observations are excluded from verified real-world evaluation.')

def verify(ident,*,status,evidence,reviewer,transport_source_id=None):
 if status not in ['verified','rejected']:raise ValueError('Review status must be verified or rejected')
 if not evidence.strip() or not reviewer.strip():raise ValueError('Evidence reference and reviewer role are required')
 with store.connect() as db:
  row=db.execute('SELECT * FROM pilot_observations WHERE id=?',(ident,)).fetchone()
  if not row:raise ValueError('Observation not found')
  data=json.loads(row['normalized'])
  if status=='verified' and (row['source_type']!='real_observed' or not data.get('matched') or not data.get('trip_id')):raise ValueError('Only exactly matched, genuine observations can be verified; simulation and unresolved records are excluded')
  if transport_source_id:data['transport_source_id']=transport_source_id
  if status=='verified':
   for previous in db.execute("SELECT id,normalized,review FROM pilot_observations WHERE kind=? AND status='verified' AND id!=?",(row['kind'],ident)).fetchall():
    p=json.loads(previous['normalized'])
    if all(p.get(k)==data.get(k) for k in ['transport_source_id','trip_id','service_date','stop_id']):
     history=json.loads(previous['review']) if previous['review'] else [];history.append(dict(status='rejected',evidence='Superseded by reviewed observation '+ident,reviewer_role=reviewer,reviewed_at=store.stamp()))
     db.execute("UPDATE pilot_observations SET status='rejected',review=? WHERE id=?",(store.json_value(history),previous['id']))
  audit=dict(previous_status=row['status'],status=status,evidence=evidence,reviewer_role=reviewer,reviewed_at=store.stamp())
  old=json.loads(row['review']) if row['review'] else [];old.append(audit)
  db.execute('UPDATE pilot_observations SET status=?,normalized=?,review=? WHERE id=?',(status,store.json_value(data),store.json_value(old),ident))
 return audit

def record_forecast(result,service_date):
 # Append-only forward forecasts, with one sample/method/event/minute to bound storage.
 created=store.stamp();sid=result['metadata'].get('source_id');data={**result,'created_at':created,'service_date':service_date}
 values=[(result['metadata']['method'],result['arrival_at']),( 'scheduled_baseline',result['scheduled_at'])]
 with store.connect() as db:
  for method,predicted in set(values):
   identity=hashlib.sha256(store.json_value([sid,result['trip_id'],service_date,result['target_stop'],method,created[:16]]).encode()).hexdigest()
   db.execute('INSERT OR IGNORE INTO forecasts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(identity,created,sid,'real_observed',result['trip_id'],service_date,result['target_stop'],method,FORECAST_VERSION,predicted,result['crowding'],store.json_value(data)))

def export_verified_history(path):
 """Export previously issued forecasts paired only with reviewed arrival events."""
 from .feeds import trip_info
 fields=['vehicle_id','trip_id','route_id','stop_id','direction','service_date','segment_index','stops_remaining','observed_at','actual_arrival_at','scheduled_arrival_at','progress_arrival_at','source_type']
 rows=[]
 with store.connect() as db:
  for observation in db.execute("SELECT normalized FROM pilot_observations WHERE kind='arrival' AND source_type='real_observed' AND status='verified'"):
   label=json.loads(observation[0]);info=trip_info(label['trip_id'])
   if not info:continue
   candidates=db.execute("SELECT * FROM forecasts WHERE source_id=? AND trip_id=? AND service_date=? AND stop_id=? AND source_mode='real_observed' AND method!='scheduled_baseline' ORDER BY created_at",(label['transport_source_id'],label['trip_id'],label['service_date'],label['stop_id'])).fetchall()
   for forecast in candidates:
    payload=json.loads(forecast['payload']);lead=(instant(label['event_at'])-instant(forecast['created_at'])).total_seconds()
    if not 120<=lead<=1800 or payload.get('segment_index') is None:continue
    rows.append(dict(vehicle_id=payload['vehicle_id'],trip_id=label['trip_id'],route_id=label['route_id'],stop_id=label['stop_id'],direction=str(info['trip'].get('direction_id') or '0'),service_date=datetime.strptime(label['service_date'],'%Y%m%d').date().isoformat(),segment_index=payload['segment_index'],stops_remaining=payload['stops_remaining'],observed_at=forecast['created_at'],actual_arrival_at=label['event_at'],scheduled_arrival_at=payload['scheduled_at'],progress_arrival_at=forecast['predicted_at'],source_type='real_observed'))
    break
 if not rows:raise ValueError('No verified arrivals have eligible, previously recorded feature-bearing forecasts to export')
 rows.sort(key=lambda r:(r['service_date'],r['trip_id'],r['observed_at']))
 output=Path(path)
 if output.exists():raise ValueError('Export already exists; choose a new path to preserve raw data')
 with output.open('w',newline='',encoding='utf-8') as file:
  writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader();writer.writerows(rows)
 digest=hashlib.sha256(output.read_bytes()).hexdigest()
 with store.connect() as db:db.execute('INSERT OR IGNORE INTO verified_exports VALUES (?,?,?)',(digest,store.stamp(),'Reviewed genuine labels paired with pre-arrival prediction ledger'))
 return dict(rows=len(rows),sha256=digest,path=str(output))

def matched_pairs():
 pairs=[]
 with store.connect() as db:
  labels=db.execute("SELECT * FROM pilot_observations WHERE status='verified' AND source_type='real_observed'").fetchall()
  for row in labels:
   label=json.loads(row['normalized']);event=instant(label['event_at'])
   forecasts=db.execute("SELECT * FROM forecasts WHERE source_id=? AND trip_id=? AND service_date=? AND stop_id=? AND source_mode='real_observed' AND created_at<? ORDER BY created_at DESC",(label['transport_source_id'],label['trip_id'],label['service_date'],label['stop_id'],event.isoformat())).fetchall()
   seen=set()
   for forecast in forecasts:
    if forecast['model_version']!=FORECAST_VERSION:continue
    created=instant(forecast['created_at']);lead=(event-created).total_seconds()
    if not 120<=lead<=1800:continue
    data=json.loads(forecast['payload'])
    if label.get('vehicle_id') and data.get('vehicle_id')!=label['vehicle_id']:continue
    if forecast['method'] in seen:continue
    seen.add(forecast['method']);key=store.json_value([label['transport_source_id'],label['trip_id'],label['service_date'],label['stop_id'],row['kind']])
    pairs.append(dict(key=key,kind=row['kind'],group=label['service_date']+'|'+label['trip_id'],source_id=label['transport_source_id'],route_id=label['route_id'],method=forecast['method'],created_at=forecast['created_at'],event_at=label['event_at'],predicted_at=forecast['predicted_at'],error_minutes=(instant(forecast['predicted_at'])-event).total_seconds()/60,actual_category=label.get('category'),predicted_category=forecast['crowding'],exact_count=label.get('passenger_count')))
 return list({(p['key'],p['method']):p for p in pairs}.values())

def conformal_radius(residuals,target=.9):
 if not residuals:raise ValueError('Calibration residuals are empty')
 ordered=sorted(abs(float(r)) for r in residuals);rank=min(len(ordered),math.ceil((len(ordered)+1)*target));return ordered[rank-1]
def evaluate_real():
 pairs=matched_pairs();arrivals=[p for p in pairs if p['kind']=='arrival'];methods=sorted({p['method'] for p in arrivals});common={p['key'] for p in arrivals if p['method']=='scheduled_baseline'} or {p['key'] for p in arrivals}
 comparable=[p for p in arrivals if p['key'] in common];events={p['key']:p for p in comparable};groups=sorted({p['group'] for p in comparable},key=lambda g:min(instant(p['event_at']) for p in comparable if p['group']==g))
 a=int(len(groups)*.6);b=int(len(groups)*.8);parts=dict(train=set(groups[:a]),calibration=set(groups[a:b]),test=set(groups[b:]));minimum=max(30,int(os.getenv('CALIBRATION_MIN_SAMPLES','30')))
 report=dict(paired_comparisons={},model_version=FORECAST_VERSION,source_type='real_observed',label='Verified forward forecasts; small samples are diagnostic only',created_at=store.stamp(),methods={},split={part:dict(trips=len(gs),rows=len({p['key'] for p in comparable if p['group'] in gs})) for part,gs in parts.items()},occupancy=None,ml_enabled=False,verified_events=len(events),reliable=len(groups)>=10 and all(len({p['key'] for p in comparable if p['group'] in gs})>=minimum for gs in parts.values()),message='Insufficient verified real-world observations for reliable evaluation.')
 for method in methods:
  series=[p for p in comparable if p['method']==method];cal=[p for p in series if p['group'] in parts['calibration']];test=[p for p in series if p['group'] in parts['test']]
  # Purge calibration events that occur after the first test forecast was issued.
  if test:cal=[p for p in cal if instant(p['event_at'])<min(instant(t['created_at']) for t in test)]
  radius=conformal_radius([p['error_minutes'] for p in cal]) if len(cal)>=minimum else None
  interval=dict(coverage=sum(abs(p['error_minutes'])<=radius for p in test)/len(test),mean_width_minutes=radius*2,test_samples=len(test),calibration_samples=len(cal),target_coverage=.9,calibration_start=min(p['event_at'] for p in cal),calibration_end=max(p['event_at'] for p in cal)) if radius is not None and test else None
  scope=test if test else series
  report['methods'][method]=dict(metrics=metrics([p['error_minutes'] for p in scope]),interval=interval,per_route={route:metrics([p['error_minutes'] for p in scope if p['route_id']==route]) for route in {p['route_id'] for p in scope}},by_source={sid:metrics([p['error_minutes'] for p in scope if p['source_id']==sid]) for sid in {p['source_id'] for p in scope}},by_hour={hour:metrics([p['error_minutes'] for p in scope if instant(p['event_at']).astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata')).hour==hour]) for hour in {instant(p['event_at']).astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata')).hour for p in scope}})
  eligible=bool(report['reliable'] and interval and interval['coverage']>=.8 and len(test)>=minimum)
  # Persist a candidate per route/source only when the method's scope is unambiguous.
  if eligible and len({(p['route_id'],p['source_id']) for p in series})==1:
   spec=dict(model_version=FORECAST_VERSION,version='split-conformal-v1',method=method,source_id=series[0]['source_id'],route_id=series[0]['route_id'],radius_minutes=radius,eligible=True,interval=interval,created_at=store.stamp())
   with store.connect() as db:db.execute('INSERT INTO calibrations VALUES (?,?,?,0)',(uuid.uuid4().hex,store.stamp(),store.json_value(spec)))
 baseline={p['key']:p for p in comparable if p['method']=='scheduled_baseline'}
 for method in methods:
  if method=='scheduled_baseline':continue
  scope=[p for p in comparable if p['method']==method and p['key'] in baseline and (not parts['test'] or p['group'] in parts['test'])]
  report['paired_comparisons'][method]=dict(sample_count=len(scope),method_metrics=metrics([p['error_minutes'] for p in scope]),schedule_metrics=metrics([baseline[p['key']]['error_minutes'] for p in scope]),note='Same eligible arrival events for this pairwise comparison; different methods may cover different subsets.')
 crowd=[p for p in pairs if p['kind']=='occupancy' and p['actual_category'] and p['predicted_category'] in ['Low','Moderate','High']]
 if crowd:report['occupancy']=dict(forecast=occupancy_metrics([p['actual_category'] for p in crowd],[p['predicted_category'] for p in crowd]),majority_baseline=None,exact_count_evaluation=None,note='Categorical outcomes only; no exact passenger-count forecast is inferred.')
 if report['reliable']:report['message']='Verified forward forecasts on chronological held-out trips. See sample counts and scope.'
 with store.connect() as db:db.execute('INSERT INTO pilot_evaluations VALUES (?,?,?)',(uuid.uuid4().hex,store.stamp(),store.json_value(report)))
 return report
def latest_evaluation():
 with store.connect() as db:row=db.execute('SELECT payload FROM pilot_evaluations ORDER BY created_at DESC LIMIT 1').fetchone()
 return json.loads(row[0]) if row else None
def calibration_status():
 with store.connect() as db:rows=[dict(id=r['id'],active=bool(r['active']) and (store.now()-instant(r['created_at'])).days<=30,**json.loads(r['payload'])) for r in db.execute('SELECT * FROM calibrations ORDER BY created_at DESC')]
 return dict(available=any(r['active'] for r in rows),candidates=rows[:10],message='Calibrated intervals available only for matching authorized source/route/method.' if any(r['active'] for r in rows) else 'Calibration unavailable: insufficient eligible verified observations. Heuristic ranges remain active.')
def activate_calibration(ident):
 with store.connect() as db:
  row=db.execute('SELECT payload FROM calibrations WHERE id=?',(ident,)).fetchone()
  if not row or not json.loads(row[0]).get('eligible'):raise ValueError('Calibration is not eligible')
  data=json.loads(row[0])
  for old in db.execute('SELECT id,payload FROM calibrations WHERE active=1').fetchall():
   previous=json.loads(old['payload'])
   if all(previous[k]==data[k] for k in ['method','source_id','route_id']):db.execute('UPDATE calibrations SET active=0 WHERE id=?',(old['id'],))
  db.execute('UPDATE calibrations SET active=1 WHERE id=?',(ident,))
def calibrated_bounds(method,route_id,remaining,fallback):
 from .feeds import source_id
 for candidate in calibration_status()['candidates']:
  if candidate['active'] and candidate['eligible'] and candidate.get('model_version')==FORECAST_VERSION and candidate['method']==method and candidate['route_id']==route_id and candidate['source_id']==source_id() and (store.now()-instant(candidate['created_at'])).days<=30:
   return {**fallback,'kind':'empirical','calibrated':True,'label':'Range estimated from eligible verified historical forecast errors; holdout coverage measured','lower_minutes':max(0,remaining/60-candidate['radius_minutes']),'upper_minutes':remaining/60+candidate['radius_minutes'],'calibration_version':candidate['id']}
 return fallback

@router.get('/data-sources/status')
@router.get('/data-health')
def data_health():
 from .feeds import health
 result=health();result['calibration']=calibration_status();result['calibration_available']=result['calibration']['available'];return result
@router.get('/predictions/evaluation')
def evaluation_endpoint():return latest_evaluation() or dict(message='Insufficient verified real-world observations for reliable evaluation.',methods={},verified_events=0)
@router.get('/predictions/calibration-status')
def calibration_endpoint():return calibration_status()

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
 review=sub.add_parser('review');review.add_argument('id');review.add_argument('--status',choices=['verified','rejected'],required=True);review.add_argument('--evidence',required=True);review.add_argument('--reviewer-role',required=True);review.add_argument('--transport-source')
 sub.add_parser('evaluate');sub.add_parser('list')
 activate=sub.add_parser('activate-calibration');activate.add_argument('id')
 export=sub.add_parser('export-history');export.add_argument('file')
 imp=sub.add_parser('import-labels');imp.add_argument('file');imp.add_argument('--license',required=True)
 args=parser.parse_args()
 try:
  if args.command=='review':print(json.dumps(verify(args.id,status=args.status,evidence=args.evidence,reviewer=args.reviewer_role,transport_source_id=args.transport_source)))
  elif args.command=='evaluate':print(json.dumps(evaluate_real(),indent=2))
  elif args.command=='activate-calibration':activate_calibration(args.id);print('Activated eligible calibration')
  elif args.command=='export-history':print(json.dumps(export_verified_history(args.file)))
  elif args.command=='list':
   with store.connect() as db:print(json.dumps([dict(r) for r in db.execute('SELECT id,kind,event_at,source_type,status FROM pilot_observations')],indent=2))
  else:
   with open(args.file,encoding='utf-8-sig') as file:
    for row in csv.DictReader(file):
     kind=row.pop('kind');row={key:value for key,value in row.items() if value.strip()};print(json.dumps(submit(PilotObservation(**row),kind,administrative=True,source_license=args.license)))
 except (ValueError,HTTPException) as exc:parser.exit(2,str(getattr(exc,'detail',exc))+'\n')
