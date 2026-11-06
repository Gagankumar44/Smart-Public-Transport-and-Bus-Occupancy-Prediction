"""Private, local CSV ingestion and leakage-aware prediction evaluation.

Run with --help. No raw observation or training mutation HTTP endpoints exist.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import sqlite3
import uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
DB_PATH=ROOT/'data/observations.db'
FEATURES=['scheduled_remaining_minutes','stops_remaining','hour','weekday','recent_segment_seconds','recent_segment_missing']
def connect(path=None):
 db=sqlite3.connect(path or DB_PATH);db.row_factory=sqlite3.Row
 db.executescript('''CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, metadata TEXT, raw BLOB, status TEXT);
 CREATE TABLE IF NOT EXISTS observations(dataset_id TEXT, row_number INTEGER, payload TEXT, PRIMARY KEY(dataset_id,row_number));
 CREATE TABLE IF NOT EXISTS features(dataset_id TEXT, row_number INTEGER, payload TEXT, PRIMARY KEY(dataset_id,row_number));
 CREATE TABLE IF NOT EXISTS evaluations(id TEXT PRIMARY KEY, dataset_id TEXT, created_at TEXT, report TEXT);
 CREATE TABLE IF NOT EXISTS prediction_outputs(evaluation_id TEXT, method TEXT, payload TEXT);
 CREATE INDEX IF NOT EXISTS observations_dataset ON observations(dataset_id);''')
 return db
def instant(value):
 t=datetime.fromisoformat(value.replace('Z','+00:00'))
 if t.utcoffset() is None:raise ValueError('Timestamp must include timezone offset')
 return t.astimezone(timezone.utc)
def feature_vector(row):
 t=instant(row['observed_at']).astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata'))
 return [(instant(row['scheduled_arrival_at'])-instant(row['observed_at'])).total_seconds()/60,
  float(row['stops_remaining']),t.hour,t.weekday(),float(row.get('recent_segment_seconds') or 0),0 if row.get('recent_segment_seconds') else 1]
def verified_dataset(digest):
 from . import pilot_store
 with pilot_store.connect() as db:return db.execute('SELECT sha256 FROM verified_exports WHERE sha256=?',(digest,)).fetchone() is not None
def import_csv(path,*,source,license_name,collected_on,mode,db_path=None):
 if mode not in ['real_observed','simulation']:raise ValueError('Mode must be real_observed or simulation')
 if not source.strip() or not license_name.strip():raise ValueError('Source and license are required')
 datetime.strptime(collected_on,'%Y-%m-%d')
 raw=Path(path).read_bytes();identity=hashlib.sha256(raw+json.dumps([source,license_name,collected_on,mode]).encode()).hexdigest()
 records=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
 meta=dict(verification_status='verified' if mode=='real_observed' and verified_dataset(hashlib.sha256(raw).hexdigest()) else 'unverified',source=source,license=license_name,collected_on=collected_on,mode=mode,sha256=hashlib.sha256(raw).hexdigest(),imported_at=datetime.now(timezone.utc).isoformat(),count=len(records),routes=[],missing={})
 with connect(db_path) as db:
  if db.execute('SELECT id FROM datasets WHERE id=?',(identity,)).fetchone():raise ValueError('This dataset and provenance were already imported')
  db.execute('INSERT INTO datasets VALUES (?,?,?,?)',(identity,json.dumps(meta),raw,'pending'))
 required=['vehicle_id','trip_id','route_id','stop_id','direction','service_date','segment_index','stops_remaining','observed_at','actual_arrival_at','scheduled_arrival_at']
 errors=[];clean=[];seen=set();last={};last_index={};arrival_labels={}
 from .main import ROUTES as DEMO_ROUTES,STOPS
 from .ground_truth import catalog
 ROUTES=catalog()['routes'] if mode=='real_observed' else DEMO_ROUTES
 for number,row in enumerate(records,2):
  try:
   missing=[field for field in required if not row.get(field)]
   if missing:raise ValueError('Missing fields: '+', '.join(missing))
   if row['route_id'] not in {r['id'] for r in ROUTES}:raise ValueError('Route is not registered in this corridor')
   if row['stop_id'] not in {s['id'] for s in STOPS}:raise ValueError('Stop is not registered in this corridor')
   for field in ['vehicle_id','trip_id']:
    if not row[field].strip() or len(row[field])>100:raise ValueError('Invalid '+field)
   r=next(r for r in ROUTES if r['id']==row['route_id'])
   if row['direction']!=r['direction']:raise ValueError('Direction does not match registered route')
   observed,actual,scheduled=[instant(row[k]) for k in ['observed_at','actual_arrival_at','scheduled_arrival_at']]
   if not 0<(actual-observed).total_seconds()<=21600:raise ValueError('Actual arrival must be within six hours after observation')
   if abs((scheduled-observed).total_seconds())>21600:raise ValueError('Scheduled arrival is outside the six-hour window')
   index=int(row['segment_index']);remaining=int(row['stops_remaining'])
   if not 0<=index<len(r['stops']) or not 0<=remaining<len(r['stops']):raise ValueError('Invalid segment or remaining stop count')
   if r['stops'].index(row['stop_id'])-index!=remaining:raise ValueError('Target stop, segment and remaining stop count disagree')
   service_date=datetime.strptime(row['service_date'],'%Y-%m-%d').date()
   if not 0<=(observed.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata')).date()-service_date).days<=1:raise ValueError('Observation is outside its GTFS service day or following day')
   group=service_date.isoformat()+'|'+row['trip_id']
   if group in last and observed<last[group]:raise ValueError('Observations are not chronological within the trip')
   if group in last_index and index<last_index[group]:raise ValueError('Segment progress moves backward within a trip')
   label_key=(group,row['stop_id'])
   if label_key in arrival_labels and arrival_labels[label_key]!=actual:raise ValueError('Actual arrival labels disagree for the same trip/stop')
   arrival_labels[label_key]=actual;last_index[group]=index
   last[group]=observed
   key=(group,row['stop_id'],observed.isoformat())
   if key in seen:raise ValueError('Duplicate observation')
   seen.add(key)
   if row.get('source_type') and row['source_type']!=mode:raise ValueError('Mixed source types in one dataset')
   if row.get('passenger_count'):
    capacity=float(row.get('capacity') or '')
    if not math.isfinite(capacity) or capacity<=0 or not 0<=float(row['passenger_count'])<=capacity:raise ValueError('Invalid count/capacity')
   for field,low,high in [('latitude',12,14),('longitude',77,78.5),('recent_segment_seconds',15,7200),('predicted_utilization',0,1)]:
    if row.get(field) and (not math.isfinite(float(row[field])) or not low<=float(row[field])<=high):raise ValueError('Invalid '+field)
   if bool(row.get('latitude'))!=bool(row.get('longitude')):raise ValueError('GPS latitude and longitude must occur together')
   if row.get('progress_arrival_at') and not 0<=(instant(row['progress_arrival_at'])-observed).total_seconds()<=21600:raise ValueError('Recorded progress prediction is outside the valid horizon')
   clean.append({**row,'group':group,'source_type':mode})
  except (ValueError,TypeError,OverflowError) as exc:errors.append(f'Row {number}: {exc}')
 if not records:errors.append('CSV contains no observations')
 meta['missing']={field:sum(not row.get(field) for row in records) for field in ['passenger_count','progress_arrival_at','predicted_utilization','latitude','recent_segment_seconds']}
 meta['routes']=sorted({r.get('route_id','') for r in records})
 if errors:meta['validation_errors']=errors[:50]
 with connect(db_path) as db:
  db.execute('UPDATE datasets SET metadata=?,status=? WHERE id=?',(json.dumps(meta),'rejected' if errors else 'ready',identity))
  if not errors:
   for i,row in enumerate(clean):
    db.execute('INSERT INTO observations VALUES (?,?,?)',(identity,i,json.dumps(row)))
    db.execute('INSERT INTO features VALUES (?,?,?)',(identity,i,json.dumps(dict(zip(FEATURES,feature_vector(row))))))
 if errors:raise ValueError('; '.join(errors[:10]))
 return identity

def split_trips(rows):
 groups={}
 for row in rows:groups.setdefault(row['group'],[]).append(row)
 ordered=sorted(groups.values(),key=lambda g:min(instant(r['observed_at']) for r in g))
 if len(ordered)<6:raise ValueError('Evaluation needs at least six distinct dated vehicle/trip groups')
 a=max(2,int(len(ordered)*.6));b=max(a+1,int(len(ordered)*.8));b=min(b,len(ordered)-1)
 train=[r for g in ordered[:a] for r in g];cal=[r for g in ordered[a:b] for r in g];test=[r for g in ordered[b:] for r in g]
 # Purge labels that would not have arrived before the next partition starts.
 cal_start=min(instant(r['observed_at']) for r in cal);test_start=min(instant(r['observed_at']) for r in test)
 train=[r for r in train if instant(r['actual_arrival_at'])<cal_start]
 cal=[r for r in cal if instant(r['actual_arrival_at'])<test_start]
 if not train or not cal or not test:raise ValueError('Insufficient non-overlapping labels after temporal purge')
 return train,cal,test
def historical_remaining(rows,row):
 peers=[r for r in rows if r['source_type']==row['source_type'] and r['route_id']==row['route_id'] and r['direction']==row['direction'] and r['segment_index']==row['segment_index'] and instant(r['actual_arrival_at'])<instant(row['observed_at'])]
 if len(peers)<3:return None
 # Smoothed ratio to scheduled remaining travel time; trained only on prior trips.
 ratios=[(instant(p['actual_arrival_at'])-instant(p['observed_at'])).total_seconds()/max(60,(instant(p['scheduled_arrival_at'])-instant(p['observed_at'])).total_seconds()) for p in peers]
 ratio=(sum(ratios)+3)/(len(ratios)+3)
 return max(0,feature_vector(row)[0]*ratio)
def metrics(errors):
 a=np.abs(np.array(errors,dtype=float))
 return dict(sample_count=len(a),mae_minutes=round(float(a.mean()),3),median_absolute_error_minutes=round(float(np.median(a)),3),p90_absolute_error_minutes=round(float(np.quantile(a,.9)),3)) if len(a) else None
def occupancy_metrics(actual,predicted):
 labels=['Low','Moderate','High'];matrix=[[0]*3 for _ in labels]
 for a,p in zip(actual,predicted):matrix[labels.index(a)][labels.index(p)]+=1
 per={};f1=[]
 for i,name in enumerate(labels):
  tp=matrix[i][i];precision=tp/max(1,sum(row[i] for row in matrix));recall=tp/max(1,sum(matrix[i]));f=2*precision*recall/(precision+recall) if precision+recall else 0
  per[name]=dict(precision=round(precision,3),recall=round(recall,3));f1.append(f)
 return dict(sample_count=len(actual),accuracy=round(sum(a==p for a,p in zip(actual,predicted))/len(actual),3),macro_f1=round(sum(f1)/3,3),labels=labels,confusion_matrix=matrix,per_class=per) if actual else None
def validate_artifact(artifact):
 if artifact.get('feature_schema')!=FEATURES or artifact.get('version')!='eta-ridge-v1':raise ValueError('Incompatible model feature schema or version')
 values=artifact.get('weights',[])
 if len(values)!=len(FEATURES)+1 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in values):raise ValueError('Invalid model coefficients')
 if artifact.get('source_type')!='real_observed':raise ValueError('Synthetic models cannot be eligible for real-data serving')
 return artifact

def evaluate(dataset_id,db_path=None,train_model=False,artifact_path=None):
 with connect(db_path) as db:
  dataset=db.execute('SELECT * FROM datasets WHERE id=?',(dataset_id,)).fetchone()
  if not dataset or dataset['status']!='ready':raise ValueError('Dataset is unavailable or failed validation')
  meta=json.loads(dataset['metadata']);rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM observations WHERE dataset_id=? ORDER BY row_number',(dataset_id,))]
 train,cal,test=split_trips(rows);model=None
 if train_model:
  if meta['mode']!='real_observed' or meta.get('verification_status')!='verified' or len(train)<60 or len({r['group'] for r in train})<6:raise ValueError('ML requires at least 60 genuine training labels across six training trips; synthetic training is disabled')
  x=np.array([[1]+feature_vector(r) for r in train]);y=np.array([(instant(r['actual_arrival_at'])-instant(r['observed_at'])).total_seconds()/60 for r in train])
  weights=np.linalg.solve(x.T@x+np.eye(x.shape[1])*.1,x.T@y)
  model=dict(version='eta-ridge-v1',feature_schema=FEATURES,weights=weights.tolist(),source_type=meta['mode'],dataset_id=dataset_id,provenance=meta,trained_at=datetime.now(timezone.utc).isoformat(),serving_enabled=False)
 methods=['schedule','progress','historical']+(['ridge_candidate'] if model else [])
 def predict(row,method):
  if method=='schedule':return feature_vector(row)[0]
  if method=='progress':return (instant(row['progress_arrival_at'])-instant(row['observed_at'])).total_seconds()/60 if row.get('progress_arrival_at') else None
  if method=='historical':return historical_remaining(train,row)
  return max(0,float(np.dot([1]+feature_vector(row),model['weights'])))
 report=dict(dataset_id=dataset_id,source_type=meta['mode'],label='Simulation testing only — not real-world accuracy' if meta['mode']=='simulation' else 'Imported observed labels; provenance asserted by importer',created_at=datetime.now(timezone.utc).isoformat(),split={k:dict(rows=len(v),trips=len({r['group'] for r in v})) for k,v in [('train',train),('calibration',cal),('test',test)]},methods={},occupancy=None,ml_enabled=False)
 outputs=[]
 for method in methods:
  residuals=[(instant(r['actual_arrival_at'])-instant(r['observed_at'])).total_seconds()/60-predict(r,method) for r in cal if predict(r,method) is not None]
  # Calibration residuals never touch test labels. Coverage is measured on test only.
  radius=float(np.quantile(np.abs(residuals),.9)) if len(residuals)>=10 else None
  errors=[];perroute={};covered=[]
  for row in test:
   prediction=predict(row,method)
   if prediction is None:continue
   actual=(instant(row['actual_arrival_at'])-instant(row['observed_at'])).total_seconds()/60;error=prediction-actual
   errors.append(error);perroute.setdefault(row['route_id'],[]).append(error)
   if radius is not None:covered.append(abs(error)<=radius)
   outputs.append(dict(method=method,group=row['group'],predicted_minutes=prediction,actual_minutes=actual))
  report['methods'][method]=dict(metrics=metrics(errors),per_route={k:metrics(v) for k,v in perroute.items() if len(v)>=5},interval=dict(coverage=round(sum(covered)/len(covered),3),mean_width_minutes=round(2*radius,3),calibration_samples=len(residuals),test_samples=len(covered),note='Measured holdout coverage; no guaranteed calibration') if covered else None)
 from .main import crowd
 labeled=[r for r in test if r.get('passenger_count') and r.get('predicted_utilization')]
 actual=[crowd(float(r['passenger_count'])/float(r['capacity'])) for r in labeled]
 predicted=[crowd(float(r['predicted_utilization'])) for r in labeled]
 train_labels=[crowd(float(r['passenger_count'])/float(r['capacity'])) for r in train if r.get('passenger_count')]
 majority=max(['Low','Moderate','High'],key=lambda label:train_labels.count(label))
 report['occupancy']=dict(forecast=occupancy_metrics(actual,predicted),majority_baseline=occupancy_metrics(actual,[majority]*len(actual))) if labeled else None
 if model:
  baseline=report['methods']['schedule']['metrics'];candidate=report['methods']['ridge_candidate']['metrics']
  model['evaluation']=report;model['eligible_candidate']=bool(candidate and baseline and candidate['mae_minutes']<baseline['mae_minutes']);validate_artifact(model)
  if artifact_path:
   Path(artifact_path).parent.mkdir(parents=True,exist_ok=True)
   Path(artifact_path).write_text(json.dumps(model,indent=2),encoding='utf-8')
 with connect(db_path) as db:
  eid=uuid.uuid4().hex;db.execute('INSERT INTO evaluations VALUES (?,?,?,?)',(eid,dataset_id,report['created_at'],json.dumps(report)))
  for output in outputs:db.execute('INSERT INTO prediction_outputs VALUES (?,?,?)',(eid,output['method'],json.dumps(output)))
 return report

def dataset_summary():
 with connect() as db:
  rows=[dict(**json.loads(r['metadata']),id=r['id'],status=r['status']) for r in db.execute('SELECT id,metadata,status FROM datasets')]
 # Aggregates only. No GPS traces, vehicle IDs or individual trajectories exposed.
 return dict(datasets=[{k:r[k] for k in ['id','source','license','mode','count','status','routes','missing']} for r in rows],ready_datasets=sum(r['status']=='ready' for r in rows))
def quality_summary():
 with connect() as db:
  evaluations=[json.loads(r[0]) for r in db.execute('SELECT report FROM evaluations ORDER BY created_at DESC LIMIT 20')]
 return dict(real=next((r for r in evaluations if r['source_type']=='real_observed'),None),simulation=next((r for r in evaluations if r['source_type']=='simulation'),None),ml_enabled=False,message='No real-world evaluation dataset connected yet.' if not any(r['source_type']=='real_observed' for r in evaluations) else 'Holdout evaluation on imported observations; see dataset provenance.')

def make_demo_csv(path):
 # Independent, predefined outcomes exercise the evaluation plumbing, not fleet accuracy.
 from .main import ROUTES
 fields=['vehicle_id','trip_id','route_id','stop_id','direction','service_date','segment_index','stops_remaining','observed_at','actual_arrival_at','scheduled_arrival_at','progress_arrival_at','recent_segment_seconds','passenger_count','capacity','predicted_utilization','source_type']
 start=datetime(2026,11,1,8,0,tzinfo=timezone(timedelta(hours=5,minutes=30)))
 with open(path,'w',newline='',encoding='utf-8') as file:
  writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
  for trip in range(12):
   for index in range(6):
    observed=start+timedelta(hours=trip,minutes=index);scheduled=start+timedelta(hours=trip,minutes=30)
    actual=scheduled+timedelta(minutes=[2,4,-1,3][trip%4]);progress=actual+timedelta(minutes=[1,-2,2][(trip+index)%3])
    writer.writerow(dict(vehicle_id='SYNTHETIC-'+str(trip),trip_id='synthetic-eval-'+str(trip),route_id='demo-2',stop_id='marathahalli',direction=ROUTES[1]['direction'],service_date=observed.date().isoformat(),segment_index=8+index,stops_remaining=6-index,observed_at=observed.isoformat(),scheduled_arrival_at=scheduled.isoformat(),actual_arrival_at=actual.isoformat(),progress_arrival_at=progress.isoformat(),recent_segment_seconds=180,passenger_count=[12,32,53][index%3],capacity=60,predicted_utilization=[.25,.6,.8][index%3],source_type='simulation'))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
 imp=sub.add_parser('import');imp.add_argument('csv');imp.add_argument('--source',required=True);imp.add_argument('--license',required=True);imp.add_argument('--collected-on',required=True);imp.add_argument('--mode',choices=['real_observed','simulation'],required=True)
 ev=sub.add_parser('evaluate');ev.add_argument('dataset_id');ev.add_argument('--train',action='store_true');ev.add_argument('--artifact')
 demo=sub.add_parser('demo');demo.add_argument('--output',default=str(ROOT/'data/evaluation_demo.csv'))
 args=parser.parse_args()
 try:
  if args.command=='import':print(import_csv(args.csv,source=args.source,license_name=args.license,collected_on=args.collected_on,mode=args.mode))
  elif args.command=='evaluate':print(json.dumps(evaluate(args.dataset_id,train_model=args.train,artifact_path=args.artifact),indent=2))
  else:
   make_demo_csv(args.output)
   try:dataset=import_csv(args.output,source='RushLess deterministic engineering fixture',license_name='CC0 synthetic fixture',collected_on='2026-11-05',mode='simulation')
   except ValueError as exc:
    if 'already imported' not in str(exc):raise
    with connect() as db:dataset=db.execute("SELECT id FROM datasets WHERE status='ready' AND metadata LIKE '%CC0 synthetic fixture%' ORDER BY rowid DESC").fetchone()[0]
   print(json.dumps(evaluate(dataset),indent=2))
 except (ValueError,KeyError) as exc:parser.exit(2,str(exc)+'\n')
