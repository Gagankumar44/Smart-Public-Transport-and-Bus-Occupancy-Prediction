"""RushLess published-network API, with isolated engineering simulation support."""
import math
import json
import os
import time
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from pathlib import Path

TZ = ZoneInfo('Asia/Kolkata')
ROOT = Path(__file__).resolve().parents[2]
engine = create_engine('sqlite:///' + str(ROOT / 'data/rushless.db'))
STOP_DATA = [
 ('silk','Silk Board',12.9173,77.6234),('hsr','HSR Layout',12.9200,77.6380),
 ('agara','Agara',12.9249,77.6500),('ibblur','Iblur',12.9308,77.6653),
 ('bellandur','Bellandur',12.9368,77.6785),('eco','Ecospace',12.9279,77.6810),
 ('kadubeesanahalli','Kadubeesanahalli',12.9415,77.6950),('marathahalli','Marathahalli',12.9563,77.7011),
 ('kundalahalli','Kundalahalli',12.9670,77.7140),('whitefield','Whitefield',12.9830,77.7500)]
STOPS = [dict(id=i,name=n,lat=a,lon=b,context='Outer Ring Road · Bengaluru') for i,n,a,b in STOP_DATA]
if (ROOT/'data/corridor.json').exists():
 STOPS=json.loads((ROOT/'data/corridor.json').read_text(encoding='utf-8'))['stops']
ROUTES = [dict(id=f'demo-{i+1}',name=f'DEMO {i+1:02}',direction='Whitefield bound' if i<3 else 'Silk Board bound',
 stops=([s['id'] for s in STOPS] if i<3 else [s['id'] for s in reversed(STOPS)]),
 color=['#0d9488','#5265b5','#d58a35','#426b8a','#8d63a5'][i],synthetic=True) for i in range(5)]
with engine.begin() as db:
 db.execute(text('CREATE TABLE IF NOT EXISTS stops (id TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL)'))
 for s in (STOPS if os.getenv('RUSHLESS_TEST_MODE')=='true' else []): db.execute(text('INSERT OR REPLACE INTO stops VALUES (:id,:name,:lat,:lon)'),s)
 db.execute(text('CREATE TABLE IF NOT EXISTS scenario_events (at TEXT, scenario TEXT)'))

# Keep demo geometry immutable; select the imported network only on explicit non-demo startup.
if os.getenv('RUSHLESS_TEST_MODE')!='true':
 from .network import status as network_status,stops as network_stops
 if network_status()['validation']=='not_imported':raise RuntimeError('Import a validated BMTC network before starting RushLess')
 STOPS=network_stops()
 with engine.begin() as db:
  db.execute(text('DELETE FROM stops'))
  db.execute(text('INSERT INTO stops VALUES (:id,:name,:lat,:lon)'),STOPS)
app = FastAPI(title='RushLess API',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('FRONTEND_ORIGINS','http://localhost:3000,http://127.0.0.1:3000').split(','),allow_credentials=True,allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['Content-Type'])
class Scenario(BaseModel):
 scenario: Literal['normal','traffic','peak','missing','close']
 restart: bool = False
 demand_profile: Literal['morning','afternoon','evening','low'] | None = None
 preserve_clock: bool = False
class Metadata(BaseModel):
 source: str = 'simulation'
 method: str = 'Deterministic segment and passenger-flow model'
 confidence: str = 'Medium'
 observed_at: str
 generated_at: str
 reason: str = 'Scenario consistency only; not calibrated real-world accuracy.'
 report_count: int = 0
 report_conflict: bool = False
 base_utilization: float | None = None
 evidence: str = 'Simulated passenger flow'
 uncertainty: dict | None = None
 demand_profile: str = 'morning'
 generation: str = ''
 source_id: str | None = None
 current_crowding: str | None = None
class Stop(BaseModel):
 id: str
 name: str
 lat: float
 lon: float
 context: str
 gtfs_stop_id: str | None = None
class Journey(BaseModel):
 id: str
 route_id: str
 route_name: str
 vehicle_id: str
 origin: Stop
 destination: Stop
 wait_minutes: float
 ride_minutes: float
 total_minutes: float
 arrival_at: str
 boarding_at: str
 stop_count: int
 transfers: int = 0
 crowding: str
 utilization: float | None
 metadata: Metadata
 geometry: list[list[float]]
 stops: list[Stop]
 explanation: str = ''
 score: float = 0
 recommended: bool = False
 service_date: str | None = None
 disruptions: list[dict] = Field(default_factory=list)
 legs: list[dict] = Field(default_factory=list)
 distance_km: float | None = None
class Journeys(BaseModel):
 journeys: list[Journey]
 generated_at: str
 scenario: str
 preference: str
 coverage: dict | None = None

class Simulation:
 def __init__(self): self.reset('normal')
 def reset(self,scenario):
  import uuid
  self.generation=uuid.uuid4().hex
  self.demand_profile='morning';self.corrections={}
  self.scenario=scenario; self.started=time.monotonic()
  self.epoch=datetime.now(TZ).replace(hour=8,minute=30,second=0,microsecond=0)
 def state(self):
  elapsed=time.monotonic()-self.started
  # One real second = one simulation second. Each reset replays the same scenario.
  return elapsed,self.epoch+timedelta(seconds=elapsed)
sim=Simulation()
_stop_catalog=None
_stops_by_id={}
def stop(sid):
 global _stop_catalog,_stops_by_id
 if _stop_catalog is not STOPS:
  _stops_by_id={s['id']:s for s in STOPS};_stop_catalog=STOPS
 result=_stops_by_id.get(sid)
 if not result: raise HTTPException(404,'That stop is not in the supported network.')
 return result
def route(rid):
 from .feeds import get_external_route
 if rid.startswith('gtfs:'):
  result=get_external_route(rid)
  if not result:raise HTTPException(404,'Observed route is not available.')
  return result
 result=next((r for r in ROUTES if r['id']==rid),None)
 if not result: raise HTTPException(404,'Route not found.')
 return result
def crowd(ratio): return 'Low' if ratio<.4 else 'Moderate' if ratio<=.75 else 'High'
def flow(current,index,route_index,scenario,capacity=60,demand_profile=None):
 alight=min(current,3+(index*2)%8)
 from .predictive import DEMAND_PROFILES
 board=round(([15,4,8,7,6][route_index]+index%3)*DEMAND_PROFILES[demand_profile or sim.demand_profile])+(18 if scenario=='peak' else 0)
 return min(capacity,max(0,current-alight)+board)
def vehicle(r,index,elapsed,now,lap=0,simulation=None):
 active=simulation or sim
 ids=r['stops']; duration=180*(2.6 if active.scenario=='traffic' and index==1 else 1.15 if active.scenario=='traffic' else 1)
 # Vehicles approach the first stop, then traverse ordered corridor segments.
 start=[300,540,720,360,660][index]+lap*1500
 if active.scenario=='traffic' and index==1: start+=360
 if active.scenario=='close' and index==0 and lap==1: start=420
 start+=active.corrections.get(f'SIM-{index+1}{lap}',0)
 progress=(elapsed-start)/duration
 pos=max(0,min(len(ids)-1,progress))
 segment=min(len(ids)-2,int(pos)); fraction=pos-segment
 a,b=stop(ids[segment]),stop(ids[segment+1])
 lat=a['lat']+(b['lat']-a['lat'])*fraction; lon=a['lon']+(b['lon']-a['lon'])*fraction
 # Before departure, a vehicle waits at the route origin; never extrapolate off-route.
 count=[46,8,26,20,12][index]
 if active.scenario=='close' and index==0 and lap==1: count=8
 for k in range(max(0,math.floor(progress)+1)): count=flow(count,k,index,active.scenario,demand_profile=active.demand_profile)
 stale=active.scenario=='missing'
 return dict(id=f'SIM-{index+1}{lap}',trip_id=f'{r["id"]}-trip-{lap}',route_id=r['id'],route_name=r['name'],lat=lat,lon=lon,
 next_stop=ids[min(len(ids)-1,max(0,math.floor(progress)+1))],passengers=count,capacity=60,
 source='simulation',completed=progress>=len(ids)-1,progress=progress,segment_seconds=duration,start_seconds=start,
  metadata=Metadata(generation=active.generation,observed_at=(now-timedelta(seconds=600 if stale else 0)).isoformat(),generated_at=now.isoformat(),confidence='Low' if stale else 'Medium',source='schedule' if stale else 'simulation').model_dump())
def snapshot():
 from .feeds import mode,external_snapshot
 if mode()!='simulation':return external_snapshot()
 elapsed,now=sim.state()
 return elapsed,now,[vehicle(r,i,elapsed,now,lap) for lap in range(2) for i,r in enumerate(ROUTES)]
def prediction(v,target,elapsed,now):
 if v.get('external'):
  from .feeds import external_prediction
  return external_prediction(v,target,elapsed,now)
 r=route(v['route_id']); ids=r['stops']
 if target not in ids: raise HTTPException(404,'Vehicle does not serve that stop.')
 idx=ids.index(target)
 from .predictive import select_eta,uncertainty
 base_start=[300,540,720,360,660][ROUTES.index(r)]+int(v['trip_id'].split('-')[-1])*1500
 scheduled_seconds=base_start+idx*180
 age=(now-datetime.fromisoformat(v['metadata']['observed_at'])).total_seconds()
 # Segment duration contains 165 seconds travel + 15 seconds assumed dwell at baseline.
 progress_remaining=max(0,v['start_seconds']-elapsed)+(idx-max(0,v['progress']))*v['segment_seconds']
 remaining,method,source=select_eta(mode='simulation',scheduled_remaining=scheduled_seconds-elapsed,progress_remaining=progress_remaining,observation_age=age)
 if remaining<=0 or v['completed'] or v['progress']>=idx: return None
 count=v['passengers']
 for k in range(max(0,math.floor(v['progress'])+1),idx+1): count=flow(count,k,ROUTES.index(r),sim.scenario)
 missing=sim.scenario=='missing'
 from .intelligence import blend_reports
 ratio,report_meta=blend_reports(v,target,count/60,now,sim,ROUTES,flow)
 bounds=uncertainty(remaining,max(0,idx-max(0,v['progress'])),age,sim.scenario,report_meta.get('report_conflict',False))
 metadata={**v['metadata'],**report_meta,'source':source,'method':method,'uncertainty':bounds,'demand_profile':sim.demand_profile}
 if age>120:metadata['confidence']='Low'
 elif bounds['occupancy_uncertainty']=='High':metadata['confidence']='Low'
 return dict(vehicle_id=v['id'],trip_id=v['trip_id'],route_id=r['id'],route_name=r['name'],target_stop=target,
 minutes=round(remaining/60,1),arrival_at=(now+timedelta(seconds=remaining)).isoformat(),
 scheduled_at=(sim.epoch+timedelta(seconds=scheduled_seconds)).isoformat(),delay_minutes=round((elapsed+remaining-scheduled_seconds)/60,1),
 crowding='Unknown' if missing else crowd(ratio),utilization=None if missing else round(ratio,2),metadata=metadata,uncertainty=bounds)
class PublishedFare(BaseModel):
 route_id:str
 route_name:str
 fare_id:str
 amount:float
 currency:str
class FareQuote(BaseModel):
 fares:list[PublishedFare]
 source:str
 version:str|None=None
 note:str
@app.get('/api/network/fares',response_model=FareQuote)
def published_fares(origin:str,destination:str):
 stop(origin);stop(destination)
 from .network import fares,status
 info=status()
 return dict(fares=fares(origin,destination),source=info.get('source','Published GTFS'),version=info.get('feed_info',[{}])[0].get('feed_version'),note='Published GTFS fare records; current ticket price and service class must be confirmed with the operator. No inferred fare is returned.')

@app.get('/api/network/status')
def network_status_endpoint():
 from .network import status
 from .feeds import current_records,mode
 from .history import instant
 source,records=current_records();now=datetime.now(TZ)
 positions=[r for r in records if r['kind']=='vehicle_position']
 fresh=[r for r in positions if r.get('status')=='accepted' and (now-instant(r['observed_at'])).total_seconds()<=120]
 return {**status(),'active_mode':mode(),'live_connected':bool(mode()=='authorized' and source and not source['synthetic'] and source['mode']=='authorized' and fresh),'matched_vehicle_count':len({r['vehicle_id'] for r in fresh}),'stale_observation_count':sum((now-instant(r['observed_at'])).total_seconds()>120 for r in positions),'last_valid_vehicle_observation':max((r['observed_at'] for r in fresh),default=None)}

@app.get('/api/health')
async def health():
 from .feeds import mode
 return {'status':'ok','database':'sqlite','mode':mode()}
@app.get('/api/stops/search',response_model=list[Stop])
def search(q:str=Query('',max_length=100),limit:int=Query(100,ge=1,le=10000)):
 return [s for s in STOPS if q.casefold() in s['name'].casefold()][:limit]
@app.get('/api/stops/nearby')
def nearby(lat:float=Query(...,ge=-90,le=90),lon:float=Query(...,ge=-180,le=180)):
 return sorted(STOPS,key=lambda s:(s['lat']-lat)**2+(s['lon']-lon)**2)[:3]
@app.get('/api/routes')
def routes(q:str='',limit:int=200):
 from .feeds import mode,external_routes
 return ROUTES if mode()=='simulation' else external_routes(q,limit)
@app.get('/api/routes/{rid}')
def route_detail(rid:str):
 r=route(rid)
 from .network import geometry
 shape=geometry(r.get('trip_id')) if rid.startswith('gtfs:') else []
 return {**r,'stops':[stop(s) for s in r['stops']],'geometry':shape or [[stop(s)['lat'],stop(s)['lon']] for s in r['stops']],'geometry_source':'GTFS shape' if shape else 'stop segments'}
@app.get('/api/routes/{rid}/departures')
def route_departures(rid:str,limit:int=Query(5,ge=1,le=20)):
 from .network import departures
 now=datetime.now(TZ);items=departures(rid,now,limit)
 if items is None:raise HTTPException(404,'Published route pattern not found.')
 return dict(departures=items,generated_at=now.isoformat(),source='schedule',note='Published departures from the route origin within the next seven days. No live bus position or operation is confirmed.')
@app.get('/api/routes/{rid}/monitor')
def monitor_route(rid:str,stop_index:int=Query(0,ge=0,le=500),limit:int=Query(5,ge=1,le=20)):
 from .monitoring import route_monitor
 return route_monitor(rid,stop_index,limit)
@app.get('/api/vehicles')
def vehicles(): return snapshot()[2]
@app.get('/api/vehicles/{vid}')
def get_vehicle(vid:str):
 v=next((v for v in snapshot()[2] if v['id']==vid),None)
 if not v and vid.startswith('scheduled:'):
  from .feeds import mode,scheduled_trip_vehicle
  parts=vid[len('scheduled:'):].rsplit(':',1)
  if mode()!='simulation' and len(parts)==2:
   v=scheduled_trip_vehicle(parts[0],parts[1],datetime.now(TZ))
 if not v: raise HTTPException(404,'Vehicle not found.')
 return v
@app.get('/api/vehicles/{vid}/occupancy')
def occupancy(vid:str,stop_id:str):
 elapsed,now,vs=snapshot(); v=next((v for v in vs if v['id']==vid),None)
 if not v:v=get_vehicle(vid)
 result=prediction(v,stop_id,elapsed,now)
 if not result: raise HTTPException(409,'Bus has already passed this stop.')
 return result
@app.get('/api/stops/{sid}/arrivals')
def arrivals(sid:str):
 stop(sid); elapsed,now,vs=snapshot()
 from .feeds import mode,scheduled_vehicles
 if mode()!='simulation':vs+=scheduled_vehicles(now,{(v['trip_id'],v['service_date']) for v in vs},target=sid)
 return sorted([p for v in vs if (p:=prediction(v,sid,elapsed,now))],key=lambda p:p['minutes'])
@app.get('/api/journeys',response_model=Journeys)
def journeys(origin:str,destination:str,preference:Literal['fastest','comfortable']='comfortable',limit:int=Query(3,ge=1,le=20),depart_at:datetime|None=None,max_transfers:int=Query(0,ge=0,le=1)):
 stop(origin);stop(destination)
 if origin==destination: raise HTTPException(422,'Choose two different stops.')
 from .feeds import mode
 if max_transfers==1 and mode()!='simulation':
  from .explorer import explore
  result=explore(origin,destination,sort='fastest' if preference=='fastest' else 'comfortable',max_transfers=1,window_minutes=120,duration_minutes=240,limit=limit,offset=0,depart_at=depart_at,search_id=None)
  converted=[]
  for i,p in enumerate(result['journeys']):
   first=p['legs'][0]
   converted.append(dict(id=first['trip_id'] if not p['transfers'] else 'path:'+p['id'],route_id=first['route_id'],route_name=' → '.join(l['route_name'] for l in p['legs']),vehicle_id=first['vehicle_id'],origin=p['origin'],destination=p['destination'],wait_minutes=p['boarding_wait_minutes'],ride_minutes=p['ride_minutes'],total_minutes=p['total_minutes'],arrival_at=p['arrival_at'],boarding_at=p['boarding_at'],stop_count=p['stop_count'],transfers=p['transfers'],crowding=p['crowding'],utilization=first['utilization'],metadata={**p['metadata'],'uncertainty':None},geometry=p['geometry'],stops=p['stops'],explanation=p['explanation']+(' Crowding is unknown; comfort uses the available time, transfers and source confidence.' if p['crowding']=='Unknown' and preference=='comfortable' else ''),score=p['score'],recommended=i==0,service_date=first['service_date'],legs=p['legs'],distance_km=p['distance_km']))
  return dict(journeys=converted,generated_at=result['generated_at'],scenario='external',preference=preference,coverage=result['coverage'])
 elapsed,now,vs=snapshot(); results=[]
 from .feeds import mode,scheduled_vehicles
 if depart_at is not None:
  if mode()!='schedule' or depart_at.tzinfo is None:raise HTTPException(422,'Future departure planning requires schedule mode and a timezone-aware time.')
  if not datetime.now(TZ)-timedelta(minutes=1)<=depart_at<=datetime.now(TZ)+timedelta(days=30):raise HTTPException(422,'Choose a departure between now and 30 days ahead.')
  now=depart_at.astimezone(TZ);vs=[]
 if mode()!='simulation':vs+=scheduled_vehicles(now,{(v['trip_id'],v['service_date']) for v in vs},target=origin,destination=destination)
 from .disruptions import active_alerts
 alerts=[] if depart_at is not None else active_alerts(now)
 for v in vs:
  j=journey_for_vehicle(v,origin,destination,elapsed,now,preference,alerts=alerts,include_geometry=False)
  if j:results.append(j)
 # Fixed scales avoid rank changes caused solely by adding/removing a candidate.
 for j in results:
  j['score']=journey_score(j,preference)
 # Keep the earliest eligible departure per demonstration pattern.
 earliest={}
 for j in sorted(results,key=lambda j:j['wait_minutes']): earliest.setdefault(j['route_id'],j)
 results=sorted(results if limit>3 or sim.scenario=='close' else earliest.values(),key=lambda j:j['score'])[:limit]
 for i,j in enumerate(results):
  from .network import geometry as network_geometry
  j['geometry']=(network_geometry(j['id'],j['origin'],j['destination']) if j['route_id'].startswith('gtfs:') else []) or [[s['lat'],s['lon']] for s in j['stops']]
  j['recommended']=i==0
  j['explanation']=('The quickest available journey.' if preference=='fastest' else 'Balances expected travel time and lower crowding.' if j['crowding']!='Unknown' else 'Crowding is unknown; ranked using the available timetable.') if i==0 else 'Another upcoming departure on this corridor.'
 return dict(journeys=results,generated_at=now.isoformat(),scenario=sim.scenario,preference=preference)

def journey_score(j,preference='comfortable'):
 penalty={'Low':0,'Moderate':.45,'High':1,'Unknown':.8}[j['crowding']]
 return round(j['total_minutes']/60*(.95 if preference=='fastest' else .40)+penalty*(.02 if preference=='fastest' else .50)+(.1 if j['metadata']['confidence']=='Low' else 0),4)

def journey_for_vehicle(v,origin,destination,elapsed,now,preference='comfortable',*,onboard=False,alerts=None,include_geometry=True):
 """Onboard monitoring predicts the destination without requiring reboarding."""
 from .disruptions import for_journey
 from .network import geometry as network_geometry
 a,b=stop(origin),stop(destination)
 r=v['record']['logical_route'] if v.get('external') else route(v['route_id']);ids=r['stops']
 if origin not in ids or destination not in ids:return None
 x,y=ids.index(origin),ids.index(destination)
 if x>=y:return None
 disruptions=for_journey(v,origin,destination,now,alerts)
 if any(d['blocking'] for d in disruptions):return None
 p=prediction(v,destination if onboard else origin,elapsed,now)
 if not p:return None
 if onboard:wait=0;ride=p['minutes'];boarding=now.isoformat();arrival=p['arrival_at']
 elif v.get('external'):
  end=prediction(v,destination,elapsed,now)
  if not end:return None
  wait=p['minutes'];ride=(datetime.fromisoformat(end['arrival_at'])-datetime.fromisoformat(p['arrival_at'])).total_seconds()/60;boarding=p['arrival_at'];arrival=end['arrival_at']
 else:wait=p['minutes'];ride=(y-x)*(180 if p['metadata']['source']=='schedule' else v['segment_seconds'])/60;boarding=p['arrival_at'];arrival=(datetime.fromisoformat(boarding)+timedelta(minutes=ride)).isoformat()
 if ride<0:return None
 total=round(wait+ride,1);penalty={'Low':0,'Moderate':.45,'High':1,'Unknown':.8}[p['crowding']]
 return dict(id=v['trip_id'],service_date=v.get('service_date'),route_id=r['id'],route_name=r['name'],vehicle_id=v['id'],origin=a,destination=b,wait_minutes=wait,ride_minutes=round(ride,1),total_minutes=total,arrival_at=arrival,boarding_at=boarding,stop_count=y-x,transfers=0,crowding=p['crowding'],utilization=p['utilization'],metadata=p['metadata'],geometry=((network_geometry(v['trip_id'],a,b) if v.get('external') else []) or [[stop(s)['lat'],stop(s)['lon']] for s in ids[x:y+1]]) if include_geometry else [],stops=[stop(s) for s in ids[x:y+1]],disruptions=disruptions,score=round(total/60*(.95 if preference=='fastest' else .40)+penalty*(.02 if preference=='fastest' else .50)+(.1 if p['metadata']['confidence']=='Low' else 0),4),recommended=False,explanation='Remaining journey from your confirmed stop.' if onboard else '')
@app.get('/api/system/status')
def status():
 from .feeds import mode,source_id
 _,now,vs=snapshot()
 if mode()!='simulation':return dict(active_source=next((v['metadata']['source'] for v in vs if v['metadata']['source']!='schedule'),'schedule'),mode=mode(),generation=source_id(),simulation_time=now.isoformat(),scenario='external',demand_profile=None,routes=len(routes()),stops=len(STOPS),vehicles=len(vs),demo_controls=False,data_note='Published BMTC schedules only. Live GPS, delays and crowding are not connected.' if mode()=='schedule' else 'Provider observations or historical replay on a matched GTFS corridor. No synthetic occupancy is mixed into external forecasts.')
 return dict(demand_profile=sim.demand_profile,generation=sim.generation,mode='simulation',scenario=sim.scenario,simulation_time=now.isoformat(),routes=len(ROUTES),stops=len(STOPS),vehicles=len(vs),
  data_note='Demo vehicles on the stop sequence of route 500-F from unofficial BMTC GTFS (Vonter, ODbL-1.0). Departure schedules, reverse patterns and demand are synthetic. Straight stop-to-stop geometry. No live BMTC feed.',
  demo_controls=os.getenv('ENABLE_DEMO_CONTROLS','true').lower()=='true')
@app.post('/api/demo/scenario')
def scenario(body:Scenario):
 from .feeds import mode
 if mode()!='simulation':raise HTTPException(403,'Demo mutations are available only in simulation mode.')
 if os.getenv('ENABLE_DEMO_CONTROLS','true').lower()!='true': raise HTTPException(403,'Demo controls are disabled.')
 if body.restart or (body.scenario=='normal' and not body.preserve_clock): sim.reset(body.scenario)
 else: sim.scenario=body.scenario
 if body.demand_profile:sim.demand_profile=body.demand_profile
 with engine.begin() as db: db.execute(text('INSERT INTO scenario_events VALUES (:at,:scenario)'),dict(at=datetime.now(TZ).isoformat(),scenario=body.scenario))
 return status()

from .intelligence import router as intelligence_router
app.include_router(intelligence_router)

from .predictive import router as prediction_router
app.include_router(prediction_router)
class DemoObservation(BaseModel):
 vehicle_id: str = Field(max_length=64)
 advance_seconds: int = Field(default=60,ge=0,le=120)
@app.post('/api/demo/observation')
def demo_observation(body:DemoObservation):
 from .feeds import mode
 if mode()!='simulation':raise HTTPException(403,'Demo mutations are available only in simulation mode.')
 if os.getenv('ENABLE_DEMO_CONTROLS','true').lower()!='true':raise HTTPException(403,'Demo controls are disabled.')
 v=get_vehicle(body.vehicle_id)
 if v['completed']:raise HTTPException(409,'Trip has finished.')
 sim.corrections[v['id']]=sim.corrections.get(v['id'],0)-body.advance_seconds
 with engine.begin() as db:
  db.execute(text('CREATE TABLE IF NOT EXISTS demo_observations (generation TEXT, vehicle_id TEXT, observed_at TEXT, advance_seconds INTEGER, source TEXT)'))
  db.execute(text('INSERT INTO demo_observations VALUES (:g,:v,:at,:s,:source)'),dict(g=sim.generation,v=v['id'],at=sim.state()[1].isoformat(),s=body.advance_seconds,source='simulation'))
 return get_vehicle(v['id'])

from fastapi.responses import JSONResponse
@app.middleware('http')
async def protect_mutations(request:Request,call_next):
 if request.method in ['POST','PATCH','DELETE']:
  origin=request.headers.get('origin')
  allowed=set(os.getenv('FRONTEND_ORIGINS','http://localhost:3000,http://127.0.0.1:3000').split(','))
  if (origin and origin not in allowed) or request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse(status_code=403,content={'detail':'Cross-site mutation is not allowed.'})
 return await call_next(request)
from .profiles import router as profile_router
from .ground_truth import router as pilot_router
app.include_router(profile_router)
app.include_router(pilot_router)

from .explorer import router as explorer_router
app.include_router(explorer_router)
from .demo_preview import router as demo_preview_router
app.include_router(demo_preview_router)
