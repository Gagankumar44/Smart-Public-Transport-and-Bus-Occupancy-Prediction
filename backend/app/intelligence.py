"""Ephemeral journey monitoring, scoped rerouting, and isolated demo evidence."""
import hashlib
import os
import time
import uuid
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

router=APIRouter(prefix='/api')
def core():
 from . import main
 return main
def init_db():
 m=core()
 with m.engine.begin() as db:
  db.execute(text('CREATE TABLE IF NOT EXISTS crowd_reports (id TEXT PRIMARY KEY, generation TEXT, vehicle_id TEXT, route_id TEXT, trip_id TEXT, stop_id TEXT, level TEXT, created_at TEXT, client TEXT, source TEXT)'))
def reports():
 init_db();m=core()
 with m.engine.connect() as db:
  return [dict(row) for row in db.execute(text('SELECT * FROM crowd_reports WHERE generation=:g ORDER BY created_at DESC'),{'g':m.sim.generation}).mappings()]
def fresh_reports(vehicle_id,now):
 window=float(os.getenv('REPORT_FRESHNESS_SECONDS','900'))
 # A reporter revising an observation is one source, not multiple independent votes.
 unique={}
 for r in reports():
  age=(now-datetime.fromisoformat(r['created_at'])).total_seconds()
  if r['vehicle_id']==vehicle_id and 0<=age<window:unique.setdefault(r['client'],(r,age))
 return list(unique.values())
def blend_reports(v,target,base,now,sim,routes,flow):
 ids=next(r['stops'] for r in routes if r['id']==v['route_id']); target_index=ids.index(target)
 relevant=[(r,age) for r,age in fresh_reports(v['id'],now) if ids.index(r['stop_id'])<=target_index]
 metadata=dict(base_utilization=round(base,3),report_count=len(relevant),report_conflict=False,evidence='Simulated passenger flow')
 if not relevant:return base,metadata
 values=[];weights=[];levels=set()
 for report,age in relevant:
  value={'Low':.2,'Moderate':.58,'High':.95}[report['level']]*60
  for k in range(ids.index(report['stop_id'])+1,target_index+1): value=flow(value,k,next(i for i,r in enumerate(routes) if r['id']==v['route_id']),sim.scenario)
  values.append(value/60);weights.append(1-age/float(os.getenv('REPORT_FRESHNESS_SECONDS','900')));levels.add(report['level'])
 influence=min(.45,.25*sum(weights));conflict=len(levels)>1
 if conflict: influence*=.5
 ratio=base*(1-influence)+sum(v*w for v,w in zip(values,weights))/sum(weights)*influence
 metadata.update(report_conflict=conflict,evidence='Demo passenger reports + simulated flow',confidence='Low' if conflict else v['metadata']['confidence'])
 return min(1,max(0,ratio)),metadata

class CrowdReport(BaseModel):
 vehicle_id: str = Field(max_length=64)
 route_id: str = Field(max_length=64)
 trip_id: str = Field(max_length=64)
 stop_id: str = Field(max_length=64)
 level: Literal['Low','Moderate','High']
 generation: str = Field(max_length=64)

rate_buckets={}
@router.post('/crowd-reports',status_code=201)
def submit_report(body:CrowdReport,request:Request,response:Response):
 m=core();v=m.get_vehicle(body.vehicle_id);m.stop(body.stop_id)
 if v.get('external'):raise HTTPException(409,'Use structured pilot observations for an external trip; demo reports cannot be attached to it.')
 if body.generation!=m.sim.generation: raise HTTPException(409,'The demo restarted. Refresh the journey before reporting.')
 if v['trip_id']!=body.trip_id or v['route_id']!=body.route_id: raise HTTPException(422,'Vehicle, trip and route do not match.')
 if v['completed']: raise HTTPException(409,'That simulated trip has finished.')
 ids=m.route(v['route_id'])['stops']
 if ids.index(body.stop_id)>max(0,int(v['progress'])): raise HTTPException(422,'Report a current or earlier stop, not a future observation.')
 client=request.cookies.get('rushless_reporter')
 if not client or len(client)!=32: client=uuid.uuid4().hex
 identity=hashlib.sha256(client.encode()).hexdigest(); network=hashlib.sha256((request.client.host if request.client else 'local').encode()).hexdigest()
 tick=time.monotonic()
 for key,maximum,window in [(identity,1,30),(network,15,60)]:
  rate_buckets[key]=[t for t in rate_buckets.get(key,[]) if tick-t<window]
  if len(rate_buckets[key])>=maximum: raise HTTPException(429,'Please wait before submitting another report.')
 _,now=m.sim.state()
 if any(r['client']==identity and r['trip_id']==body.trip_id and r['level']==body.level and age<60 for r,age in fresh_reports(v['id'],now)):raise HTTPException(409,'This recent report has already been recorded.')
 record=dict(id=uuid.uuid4().hex,generation=m.sim.generation,vehicle_id=v['id'],route_id=v['route_id'],trip_id=v['trip_id'],stop_id=body.stop_id,level=body.level,created_at=now.isoformat(),client=identity,source='demo_passenger_report')
 init_db()
 with m.engine.begin() as db:db.execute(text('INSERT INTO crowd_reports VALUES (:id,:generation,:vehicle_id,:route_id,:trip_id,:stop_id,:level,:created_at,:client,:source)'),record)
 for key in [identity,network]:rate_buckets[key].append(tick)
 response.set_cookie('rushless_reporter',client,httponly=True,samesite='strict',max_age=86400)
 return {k:v for k,v in record.items() if k!='client'}

@router.get('/crowd-reports/summary')
def report_summary():
 m=core();_,now=m.sim.state();window=float(os.getenv('REPORT_FRESHNESS_SECONDS','900'))
 recent=[{k:v for k,v in r.items() if k!='client'} for r in reports() if 0<=(now-datetime.fromisoformat(r['created_at'])).total_seconds()<window]
 return dict(source='demo_passenger_report',count=len(recent),reports=recent[:20])

def classify_gap(predicted,scheduled):
 if predicted>float(os.getenv('CLOSE_ARRIVAL_MINUTES','3')):return None
 return 'Potential bunching' if scheduled is not None and scheduled>=6 and predicted<scheduled*.5 else 'Close arrivals'
@router.get('/stops/{sid}/close-arrivals')
def close_arrivals(sid:str):
 m=core();items=m.arrivals(sid);groups={};result=[]
 from .feeds import mode
 if mode()!='simulation':items=[p for p in items if p['metadata']['source']=='real_observed']
 for p in items:groups.setdefault(p['route_id'],[]).append(p)
 for rid,group in groups.items():
  group.sort(key=lambda p:p['minutes'])
  for first,second in zip(group,group[1:]):
   gap=round(second['minutes']-first['minutes'],1)
   # Compare predictions with the same trip instances' published timetable.
   scheduled=abs((datetime.fromisoformat(second['scheduled_at'])-datetime.fromisoformat(first['scheduled_at'])).total_seconds())/60
   label=classify_gap(gap,scheduled)
   if label:result.append(dict(route_id=rid,direction=m.route(rid)['direction'],label=label,gap_minutes=gap,scheduled_headway_minutes=scheduled,first=first,second=second,source=first['metadata']['source'],explanation='Predicted spacing is shorter than the demo timetable. This is not confirmed real-world bunching.' if mode()=='simulation' else 'Provider predictions indicate close arrivals. This does not confirm operational bunching.'))
 return result

class WatchRequest(BaseModel):
 trip_id: str = Field(max_length=64)
 origin: str = Field(max_length=64)
 destination: str = Field(max_length=64)
 preference: Literal['fastest','comfortable']='comfortable'
 alerts_enabled: bool = True
 service_date: str | None = Field(default=None,pattern=r'^\d{8}$')

watches={}
def candidates(watch):return core().journeys(watch.get('current_stop',watch['origin']),watch['destination'],watch['preference'],20)['journeys']
def materially_better(current,alternative,mode):
 if not current:return True
 levels={'Low':0,'Moderate':1,'High':2,'Unknown':2}
 gain=current['total_minutes']-alternative['total_minutes']
 # A meaningful time saving may warrant a review even when its timetable-only
 # confidence penalty outweighs the gain in the aggregate ranking score.
 if gain>=5 and (mode=='fastest' or levels[alternative['crowding']]<=levels[current['crowding']]):return True
 return alternative['score']<=current['score']-.08 and (gain>=3 or (mode=='comfortable' and levels[current['crowding']]-levels[alternative['crowding']]>=1))
def evaluate_alerts(previous,current,emitted):
 events=[]
 if not current:
  if 'unavailable' not in emitted: events.append(('unavailable','Your selected departure is no longer boardable. Review another journey.'))
  return events
 for threshold in [int(v) for v in os.getenv('APPROACH_THRESHOLDS','5,2').split(',')]:
  key=f'approaching-{threshold}'
  if current['wait_minutes']<=threshold and (previous is None or previous['wait_minutes']>threshold) and key not in emitted:events.append((key,f'Your bus is expected in about {threshold} minutes.'))
 if previous:
  delay=(datetime.fromisoformat(current['boarding_at'])-datetime.fromisoformat(previous['boarding_at'])).total_seconds()/60
  if delay>=3:events.append(('delay',f'Your bus is now estimated to arrive {round(delay)} minutes later.'))
  if previous['crowding']!=current['crowding']:events.append(('crowding',f'Boarding forecast changed to {current["crowding"].lower()} crowding.'))
  if current['metadata']['confidence']=='Low' and previous['metadata']['confidence']!='Low':events.append(('freshness','Observation unavailable or conflicting; confidence is reduced.'))
 return events

@router.post('/watches',status_code=201)
def create_watch(body:WatchRequest):
 tick=time.monotonic()
 for key in list(watches):
  if tick-watches[key]['touched']>1800:del watches[key]
 if len(watches)>=200:raise HTTPException(503,'Journey monitoring is busy. Try again shortly.')
 watch={**body.model_dump(),'generation':core().sim.generation,'previous':None,'alerts':[],'emitted':{},'dismissed':None,'touched':tick,'phase':'waiting','current_stop':body.origin,'incident':'none'}
 current=next((j for j in candidates(watch) if j['id']==body.trip_id and (not body.service_date or j.get('service_date')==body.service_date)),None)
 if not current and body.service_date:
  from .feeds import scheduled_trip_vehicle
  m=core();elapsed,now,fleet=m.snapshot()
  selected=next((v for v in fleet if v['trip_id']==body.trip_id and v.get('service_date')==body.service_date),None) or scheduled_trip_vehicle(body.trip_id,body.service_date,now)
  if selected:current=m.journey_for_vehicle(selected,body.origin,body.destination,elapsed,now,body.preference)
  if current and current['wait_minutes']>120:current=None
 if not current:raise HTTPException(409,'That departure is no longer boardable.')
 watch.update(previous=current,delay_anchor=current,service_date=current.get('service_date'),stops=current['stops']);key=uuid.uuid4().hex;watches[key]=watch
 return dict(id=key,trip_id=body.trip_id,source=current['metadata']['source'],message='Watching while this page is open.')
def get_watch(key):
 watch=watches.get(key)
 if not watch or time.monotonic()-watch['touched']>1800:raise HTTPException(404,'Journey watch expired. Start watching again.')
 watch['touched']=time.monotonic();return watch
@router.get('/watches/{key}')
def watch_status(key:str,preference:Literal['fastest','comfortable']='comfortable',alerts_enabled:bool=True):
 m=core();w=get_watch(key);w['preference']=preference;w['alerts_enabled']=alerts_enabled
 if w['generation']!=m.sim.generation:
  w.update(generation=m.sim.generation,previous=None,delay_anchor=None,emitted={},alerts=[],dismissed=None)
 from .feeds import mode,scheduled_trip_vehicle
 from .disruptions import active_alerts,for_journey
 elapsed,now,vehicles=m.snapshot();disruptions=[]
 selected=next((v for v in vehicles if v['trip_id']==w['trip_id'] and v.get('service_date')==w.get('service_date')),None)
 if not selected and mode()!='simulation':selected=scheduled_trip_vehicle(w['trip_id'],w.get('service_date'),now)
 if w['phase']=='arrived':current=None;options=[]
 else:
  options=[j for j in candidates(w) if j['id']!=w['trip_id'] and not any(d.get('blocking') for d in j.get('disruptions',[]))]
  current=m.journey_for_vehicle(selected,w['current_stop'],w['destination'],elapsed,now,preference,onboard=w['phase']=='onboard',alerts=active_alerts(now)) if selected else None
  if selected:disruptions=for_journey(selected,w['current_stop'],w['destination'],now)
  if w['incident']!='none':
   disruptions.append(dict(id='personal:'+w['incident'],kind='commuter_report',blocking=True,message='You reported a '+('breakdown / stopped bus' if w['incident']=='breakdown' else 'route diversion')+'. This report affects only your journey watch.'))
   current=None
 best=options[0] if options else None
 tick=time.monotonic()
 if w['phase']=='arrived':events=[]
 elif w['phase']=='onboard':
  events=[]
  if current and w.get('delay_anchor'):
   delay=(datetime.fromisoformat(current['arrival_at'])-datetime.fromisoformat(w['delay_anchor']['arrival_at'])).total_seconds()/60
   if delay>=3:events.append(('delay',f'Your destination arrival is now estimated {round(delay)} minutes later.'))
  elif not current:events.append(('unavailable','A usable destination ETA is unavailable. Review departures from your confirmed stop.'))
 else:events=evaluate_alerts(w['previous'],current,w['emitted'])
 if current and not w.get('delay_anchor'):w['delay_anchor']=current
 if w['phase']=='waiting' and current and w.get('delay_anchor') and not any(kind=='delay' for kind,_ in events):
  delay=(datetime.fromisoformat(current['boarding_at'])-datetime.fromisoformat(w['delay_anchor']['boarding_at'])).total_seconds()/60
  if delay>=3:events.append(('delay',f'Your bus is now estimated to arrive {round(delay)} minutes later.'))
 if alerts_enabled:events += [('disruption:'+d['id'],d['message']) for d in disruptions]
 for kind,message in (events if alerts_enabled else []):
  if kind not in w['emitted'] or (kind in ['delay','crowding','freshness'] and tick-w['emitted'][kind]>=30):
   w['alerts'].append(dict(id=uuid.uuid4().hex,kind=kind,message=message,created_at=m.snapshot()[1].isoformat()));w['emitted'][kind]=tick
   if kind=='delay':w['delay_anchor']=current
 alternative=best if alerts_enabled and best and best['id']!=w['trip_id'] and materially_better(current,best,preference) and w['dismissed']!=best['id'] else None
 w['previous']=current;w['alerts']=w['alerts'][-12:]
 return dict(id=key,trip_id=w['trip_id'],current=current,available=current is not None,alerts=w['alerts'],alternative=alternative,source=current['metadata']['source'] if current else 'unavailable',generation=w['generation'],phase=w['phase'],current_stop=m.stop(w['current_stop']),progress_stops=w['stops'],incident=w['incident'],disruptions=disruptions,checked_at=now.isoformat(),monitoring_note='Published schedules only. Live delays, breakdowns and diversions cannot be detected without an authorized feed.' if mode()=='schedule' else 'Updates use the configured source; replay is historical and never live.',alternatives_note='Direct departures from your confirmed stop, within the next two hours. No verified transfer or detour path is inferred.' if not alternative else 'Confirm that you are at this stop before switching. Board or alight only where permitted.')

class Progress(BaseModel):
 current_stop: str = Field(max_length=64)
 phase: Literal['waiting','onboard','arrived']='onboard'
 incident: Literal['none','breakdown','diversion']='none'

@router.patch('/watches/{key}/progress')
def update_progress(key:str,body:Progress):
 w=get_watch(key);ids=[s['id'] for s in w['stops']]
 if w['phase']=='arrived':raise HTTPException(409,'This journey has finished. Start a new watch.')
 if body.current_stop not in ids or ids.index(body.current_stop)<ids.index(w['current_stop']):raise HTTPException(422,'Confirm a stop on the remaining selected journey; progress cannot move backward.')
 at_destination=body.current_stop==w['destination']
 if (body.phase=='arrived')!=at_destination:raise HTTPException(422,'Mark arrived only when you confirm the destination stop.')
 if body.phase=='waiting' and w['phase']=='onboard':raise HTTPException(422,'Use an alternative journey to change departures after boarding.')
 w.update(current_stop=body.current_stop,phase=body.phase,incident=body.incident,previous=None,delay_anchor=None,emitted={},dismissed=None)
 return watch_status(key,w['preference'],w.get('alerts_enabled',True))
class Decision(BaseModel):
 action: Literal['accept','keep']
@router.post('/watches/{key}/decision')
def decision(key:str,body:Decision):
 state=watch_status(key,get_watch(key)['preference'],get_watch(key).get('alerts_enabled',True));w=get_watch(key);alternative=state['alternative']
 if alternative:
  if body.action=='accept':w.update(trip_id=alternative['id'],origin=w['current_stop'],previous=alternative,delay_anchor=alternative,emitted={},alerts=[],dismissed=None,phase='waiting',incident='none',service_date=alternative.get('service_date'),stops=alternative['stops'])
  else:w['dismissed']=alternative['id']
 return watch_status(key,w['preference'],w.get('alerts_enabled',True))
@router.delete('/watches/{key}',status_code=204)
def delete_watch(key:str):watches.pop(key,None)

@router.get('/insights/summary')
def insights():
 m=core();elapsed,now,vs=m.snapshot()
 from .feeds import mode
 if mode()!='simulation':
  return dict(scope='Matched provider corridor',source=mode(),generated_at=now.isoformat(),active_vehicles=len(vs),average_delay_minutes=None,routes=[],reports=dict(count=0,reports=[]),warnings=[],quality='Provider delay/occupancy may be unavailable; see Data Health. No synthetic fleet metrics are used.')
 active=[v for v in vs if not v['completed']];rows=[]
 for route in m.ROUTES:
  group=[v for v in active if v['route_id']==route['id']]
  rows.append(dict(route_id=route['id'],name=route['name'],vehicles=len(group),utilization=round(sum(v['passengers']/v['capacity'] for v in group)/len(group),2) if group else 0,delay_minutes=round(sum((v['start_seconds']-([300,540,720,360,660][m.ROUTES.index(route)]+int(v['trip_id'].split('-')[-1])*1500))/60+max(0,v['progress'])*(v['segment_seconds']-180)/60 for v in group)/len(group),1) if group else 0))
 # Early departures are zero delay in this delay-only visualization.
 for row in rows: row['delay_minutes']=max(0,row['delay_minutes'])
 warnings=close_arrivals('silk')+close_arrivals('marathahalli')
 return dict(scope='Selected Bengaluru demonstration corridor',source='simulation',generated_at=now.isoformat(),active_vehicles=len(active),average_delay_minutes=round(sum(r['delay_minutes']*r['vehicles'] for r in rows)/max(1,len(active)),1),routes=rows,reports=report_summary(),warnings=warnings,quality='Schedule fallback; crowding unavailable' if m.sim.scenario=='missing' else 'Synthetic observations; not measured real-world accuracy')
