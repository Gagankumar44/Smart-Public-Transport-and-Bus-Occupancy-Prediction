"""Bounded, timetable-aware direct/one-transfer routing on the imported GTFS graph.

No nearby-stop walking edges or private-provider connections are invented.
"""
import hashlib
import heapq
import math
import threading
import time
import uuid
from collections import defaultdict
from contextlib import closing
from datetime import datetime,timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal
import numpy as np
from fastapi import APIRouter,HTTPException,Query
from . import network,feeds
from .schedule import service_active,TZ
from .history import instant

router=APIRouter(prefix='/api/journeys')
LOCK=threading.RLock()
SEARCH_SLOTS=threading.BoundedSemaphore(2)
SNAPSHOTS={}
MAX_TEMPLATES=240
MAX_INSTANCES=1000
MAX_RESULTS=80
SEARCH_SECONDS=6
TRANSFER_SECONDS=180
SORTS=Literal['recommended','shortest','fastest','fewest_transfers','comfortable']

def version():
 p=network.active_path()
 return str(p.resolve()),p.stat().st_mtime_ns

@lru_cache(maxsize=2)
def graph(path,mtime):
 """Ordered stop-pattern graph, constructed once per immutable dataset version."""
 patterns={};at=defaultdict(list)
 with closing(network.connect()) as db:
  stops={r['stop_id']:dict(r) for r in db.execute('SELECT * FROM stops')}
  for row in db.execute('''SELECT p.id,p.trip_id,p.route_id,r.route_short_name,s.stop_id,s.seq FROM network_patterns p
   JOIN routes r ON r.route_id=p.route_id JOIN stop_times s ON s.trip_id=p.trip_id ORDER BY p.id,s.seq'''):
   pid=row['id']
   if pid not in patterns:patterns[pid]=dict(id=pid,trip_id=row['trip_id'],route_id=row['route_id'],name=row['route_short_name'] or row['route_id'],stops=[])
   index=len(patterns[pid]['stops']);patterns[pid]['stops'].append(row['stop_id']);at[row['stop_id']].append((pid,index))
 for p in patterns.values():
  p['chord']=[0.]
  for a,b in zip(p['stops'],p['stops'][1:]):
   sa,sb=stops[a],stops[b];p['chord'].append(p['chord'][-1]+haversine((float(sa['stop_lat']),float(sa['stop_lon'])),(float(sb['stop_lat']),float(sb['stop_lon']))))
 return dict(patterns=patterns,at=at,stops=stops)

def haversine(a,b):
 lat1,lat2=math.radians(a[0]),math.radians(b[0]);dlat=lat2-lat1;dlon=math.radians(b[1]-a[1])
 return 6371.0088*2*math.asin(min(1,math.sqrt(math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2)))

@lru_cache(maxsize=512)
def pattern_geometry(path,mtime,pid):
 g=graph(path,mtime);p=g['patterns'][pid]
 coordinates=[[float(g['stops'][sid]['stop_lat']),float(g['stops'][sid]['stop_lon'])] for sid in p['stops']]
 shape=network.geometry(p['trip_id']);method='GTFS shape'
 if shape:
  array=np.asarray(shape);indices=[];cursor=0
  for lat,lon in coordinates:
   squared=(array[cursor:,0]-lat)**2+((array[cursor:,1]-lon)*math.cos(math.radians(lat)))**2
   index=cursor+int(np.argmin(squared))
   if haversine([lat,lon],shape[index])>1:shape=[];break
   indices.append(index);cursor=index
  if shape and any(a==b for a,b in zip(indices,indices[1:])):shape=[]
 if not shape:
  shape=coordinates;indices=list(range(len(shape)));method='Stop-segment estimate; shape missing or not aligned'
 cumulative=[0.]
 for a,b in zip(shape,shape[1:]):cumulative.append(cumulative[-1]+haversine(a,b))
 return shape,indices,cumulative,method

def segment_metric(key,pid,x,y):
 points,indices,cumulative,method=pattern_geometry(*key,pid)
 a,b=indices[x],indices[y]
 return dict(distance_km=round(cumulative[b]-cumulative[a],3),geometry=points[a:b+1],distance_method=method,measured=method=='GTFS shape')

@lru_cache(maxsize=256)
def timetable(path,mtime,pid):
 with closing(network.connect()) as db:
  rows=db.execute('''SELECT t.trip_id,t.service_id,s.* FROM trip_patterns p JOIN trips t ON t.trip_id=p.trip_id
   JOIN stop_times s ON s.trip_id=t.trip_id WHERE p.pattern_id=? ORDER BY t.trip_id,s.seq''',(pid,)).fetchall()
 trips={}
 for row in rows:
  item=trips.setdefault(row['trip_id'],dict(trip_id=row['trip_id'],service_id=row['service_id'],times=[]));item['times'].append(dict(row))
 return list(trips.values())

def templates(g,origin,destination,max_transfers):
 """Two-round stop-pattern graph expansion; priority queue bounds path templates."""
 direct=[];connecting=[];incoming=defaultdict(list)
 for pid,y in g['at'].get(destination,[]):
  for z,sid in enumerate(g['patterns'][pid]['stops'][:y]):incoming[sid].append((pid,z,y))
 for pid,x in g['at'].get(origin,[]):
  p=g['patterns'][pid];ids=p['stops']
  for y in range(x+1,len(ids)):
   segment=ids[x:y+1]
   if len(set(segment))!=len(segment):break
   if ids[y]==destination:direct.append(((pid,x,y),));break
   if not max_transfers:continue
   for other,z,end in incoming.get(ids[y],[]):
    if other==pid:continue
    tail=g['patterns'][other]['stops'][z:end+1]
    complete=segment+tail[1:]
    if len(set(complete))!=len(complete):continue
    connecting.append(((pid,x,y),(other,z,end)))
    if len(connecting)>=20000:break
   if len(connecting)>=20000:break
  if len(connecting)>=20000:break
 def lower(plan):
  # Stop chords are a search priority only; displayed metrics use actual geometry.
  result=0
  for pid,x,y in plan:
   cumulative=g['patterns'][pid]['chord'];result+=cumulative[y]-cumulative[x]
  return result
 unique=list(dict.fromkeys(direct));remaining=MAX_TEMPLATES-min(len(unique),MAX_TEMPLATES)
 chosen=unique[:MAX_TEMPLATES]+heapq.nsmallest(max(0,remaining),dict.fromkeys(connecting),key=lower)
 return chosen,len(unique)+len(set(connecting))>len(chosen) or len(connecting)>=20000

class Search:
 def __init__(self,origin,destination,clock,window,duration,max_transfers):
  from . import main
  self.key=version()
  with LOCK:self.g=graph(*self.key)
  self.origin=feeds.original(origin);self.destination=feeds.original(destination);self.clock=clock
  self.deadline=clock+timedelta(minutes=duration);self.first_deadline=clock+timedelta(minutes=window)
  self.max_transfers=max_transfers;self.instances=0;self.limited=False;self.started=time.monotonic();self.options_cache={}
  self.vehicles={};self.alerts=[]
  if abs((datetime.now(TZ)-clock).total_seconds())<60:
   from .disruptions import active_alerts
   if feeds.mode()!='schedule':
    _,_,vs=main.snapshot();self.vehicles={(v['trip_id'],v.get('service_date')):v for v in vs if v.get('external') and v['record'].get('kind')}
   self.alerts=active_alerts(clock)
  self.db=network.connect();self.tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  self.imported_at=network.status().get('imported_at',clock.isoformat());self.predictions={}
 def close(self):self.db.close()
 def capped(self):
  if self.instances>=MAX_INSTANCES or time.monotonic()-self.started>=SEARCH_SECONDS:self.limited=True;return True
  return False
 def leg(self,pid,x,y,tid,date):
  from . import main
  from .disruptions import for_journey
  v=self.vehicles.get((tid,date))
  if not v:
   v=feeds.scheduled_trip_vehicle(tid,date,self.clock,service_verified=True,imported_at=self.imported_at)
   if v:self.vehicles[(tid,date)]=v
  if not v:return None
  info=feeds.trip_info(tid);times=info['times']
  if str(times[x].get('pickup_type','0') or '0')!='0' or str(times[y].get('drop_off_type','0') or '0')!='0':return None
  a,b=times[x]['id'],times[y]['id']
  if any(d['blocking'] for d in for_journey(v,a,b,self.clock,self.alerts,origin_index=x,destination_index=y)):return None
  def predicted(sid,index):
   key=(tid,date,index)
   if key not in self.predictions:self.predictions[key]=feeds.external_prediction(v,sid,0,self.clock,target_index=index)
   return self.predictions[key]
  start=predicted(a,x);end=predicted(b,y)
  scheduled_start=feeds.service_stamp(date,times[x]['departure_seconds'] if 'departure_seconds' in times[x] else times[x]['seconds'])
  if not end:return None
  if not start:
   if v['metadata']['source']!='schedule' or scheduled_start<self.clock:return None
   start={**end,'arrival_at':scheduled_start.isoformat(),'metadata':{**end['metadata'],'source':'schedule'}}
  boarding=instant(start['arrival_at'])
  if start['metadata']['source']=='schedule':boarding=scheduled_start
  arrival=instant(end['arrival_at'])
  if arrival<=boarding or arrival>self.deadline:return None
  p=self.g['patterns'][pid];metric=segment_metric(self.key,pid,x,y)
  stops=[]
  delay=(arrival-feeds.service_stamp(date,times[y]['seconds'])).total_seconds()
  for i in range(x,y+1):
   stop=main.stop(times[i]['id']);passing=feeds.service_stamp(date,times[i]['seconds'])
   stops.append({**stop,'order':i-x+1,'arrival_at':passing.isoformat() if end['metadata']['source']=='schedule' else None})
  return dict(id=tid+':'+date+':'+str(x)+':'+str(y),trip_id=tid,service_date=date,route_id=pid,route_name=p['name'],vehicle_id=v['id'],origin=stops[0],destination=stops[-1],boarding_at=boarding.isoformat(),arrival_at=arrival.isoformat(),ride_minutes=round((arrival-boarding).total_seconds()/60,2),wait_minutes=round((boarding-self.clock).total_seconds()/60,1),total_minutes=round((arrival-self.clock).total_seconds()/60,1),stop_count=y-x,stops=stops,crowding=start['crowding'],utilization=start.get('utilization'),metadata=end['metadata'],delay_minutes=round(delay/60,1),**metric)
 def options(self,pid,x,y):
  k=(pid,x,y)
  if k in self.options_cache:return self.options_cache[k]
  result=[]
  for item in timetable(*self.key,pid):
   times=item['times']
   for offset in [-1,0,1]:
    if self.capped():break
    day=(self.clock+timedelta(days=offset)).astimezone(TZ).replace(hour=0,minute=0,second=0,microsecond=0);date=day.strftime('%Y%m%d')
    departure=day+timedelta(seconds=times[x]['departure_seconds'])
    if (item['trip_id'],date) not in self.vehicles and not self.clock<=departure<=self.deadline:continue
    if not service_active(self.db,item['service_id'],day):continue
    self.instances+=1
    leg=self.leg(pid,x,y,item['trip_id'],date)
    if leg:result.append(leg)
  result.sort(key=lambda l:l['boarding_at']);self.options_cache[k]=result
  return result
 def transfer_seconds(self,first,second):
  if 'transfers' not in self.tables:return TRANSFER_SECONDS
  sid=feeds.original(first['destination']['id']);rules=[dict(r) for r in self.db.execute('SELECT * FROM transfers WHERE from_stop_id=? AND to_stop_id=?',(sid,sid))]
  for rule in rules:
   checks={'from_route_id':self.g['patterns'][first['route_id']]['route_id'],'to_route_id':self.g['patterns'][second['route_id']]['route_id'],'from_trip_id':first['trip_id'],'to_trip_id':second['trip_id']}
   if any(rule.get(k) and str(rule[k])!=str(v) for k,v in checks.items()):continue
   if str(rule.get('transfer_type'))=='3':return None
   if rule.get('min_transfer_time'):return max(TRANSFER_SECONDS,int(rule['min_transfer_time']))
  return TRANSFER_SECONDS
 def build(self,legs):
  from .main import journey_score
  boarding=instant(legs[0]['boarding_at']);arrival=instant(legs[-1]['arrival_at'])
  ride=sum(l['ride_minutes'] for l in legs);total=(arrival-self.clock).total_seconds()/60;wait=total-ride
  if boarding>self.first_deadline or boarding<self.clock:return None
  levels={'Low':0,'Moderate':1,'High':2,'Unknown':3};crowding=max((l['crowding'] for l in legs),key=lambda c:levels[c])
  source=legs[0]['metadata']['source'] if all(l['metadata']['source']==legs[0]['metadata']['source'] for l in legs) else 'mixed'
  meta={**legs[0]['metadata'],'source':source,'confidence':'Low' if any(l['metadata']['confidence']=='Low' for l in legs) else 'Medium'}
  stops=legs[0]['stops']+(legs[1]['stops'][1:] if len(legs)>1 else [])
  ident=hashlib.sha256('|'.join(l['id'] for l in legs).encode()).hexdigest()[:24]
  j=dict(id=ident,origin=legs[0]['origin'],destination=legs[-1]['destination'],legs=legs,transfers=len(legs)-1,transfer_stop=legs[0]['destination'] if len(legs)>1 else None,walking_km=0.,distance_km=round(sum(l['distance_km'] for l in legs),3),bus_distance_km=round(sum(l['distance_km'] for l in legs),3),distance_measured=all(l['measured'] for l in legs),total_minutes=round(total,1),wait_minutes=round(wait,1),boarding_wait_minutes=round((boarding-self.clock).total_seconds()/60,1),transfer_wait_minutes=round(wait-(boarding-self.clock).total_seconds()/60,1),ride_minutes=round(ride,1),boarding_at=boarding.isoformat(),arrival_at=arrival.isoformat(),stop_count=sum(l['stop_count'] for l in legs),intermediate_stops=max(0,len(stops)-2),stops=stops,geometry=[point for l in legs for point in l['geometry']],crowding=crowding,metadata=meta,badges=[],explanation='')
  j['score']=journey_score(j,'comfortable')+.12*j['transfers'];return j
 def run(self):
  plans,limited=templates(self.g,self.origin,self.destination,self.max_transfers);self.limited|=limited;journeys=[];processed=0
  for plan in plans:
   if self.capped():break
   processed+=1
   first_options=self.options(*plan[0]);first_options=[l for l in first_options if self.clock<=instant(l['boarding_at'])<=self.first_deadline]
   # Two useful departures per template, separated by at least ten minutes.
   retained=[]
   for first in first_options:
    if retained and (instant(first['boarding_at'])-instant(retained[-1]['boarding_at'])).total_seconds()<600:continue
    retained.append(first)
    if len(retained)==2:break
   if first_options:
    quickest=min(first_options,key=lambda l:l['arrival_at'])
    if quickest not in retained:retained.append(quickest)
   for first in retained:
    if len(plan)==1:
     j=self.build([first])
     if j:journeys.append(j)
    else:
     choices=[]
     for second in self.options(*plan[1]):
      buffer=self.transfer_seconds(first,second)
      if buffer is not None and second['trip_id']!=first['trip_id'] and instant(second['boarding_at'])>=instant(first['arrival_at'])+timedelta(seconds=buffer):choices.append(second)
     if choices:
      for second in sorted(choices,key=lambda l:l['arrival_at'])[:2]:
       j=self.build([first,second])
       if j:journeys.append(j)
  unique={}
  for j in journeys:
   # Changing between the same two trip instances at several shared stops does
   # not need several cards. Keep the strongest of those interchange choices.
   identity=tuple((l['trip_id'],l['service_date'],l['route_id']) for l in j['legs'])
   prior=unique.get(identity)
   if not prior or (not j['distance_measured'],j['distance_km'],j['total_minutes'])<(not prior['distance_measured'],prior['distance_km'],prior['total_minutes']):unique[identity]=j
  items=list(unique.values())
  # Preserve distance/time/transfer tradeoffs, then cap the useful candidate set.
  keep={}
  for ordered in [sorted(items,key=lambda j:j['score']),sorted(items,key=lambda j:(not j['distance_measured'],j['distance_km'])),sorted(items,key=lambda j:j['total_minutes']),sorted(items,key=lambda j:(j['transfers'],j['total_minutes']))]:
   for j in ordered[:MAX_RESULTS//4]:keep[j['id']]=j
  for j in sorted(items,key=lambda j:j['score']):
   if len(keep)>=MAX_RESULTS:break
   keep[j['id']]=j
  items=list(keep.values())
  if len(unique)>MAX_RESULTS:self.limited=True
  if items:
   fastest=min(items,key=lambda j:j['total_minutes']);recommended=min(items,key=lambda j:j['score'])
   measured=[j for j in items if j['distance_measured']];shortest=min(measured,key=lambda j:j['distance_km']) if measured else None
   for j in items:
    if j is fastest:j['badges'].append('Fastest')
    if j is shortest:j['badges'].append('Shortest measured')
    if j is recommended:j['badges'].append('Recommended')
    j['explanation']=('No transfers. ' if not j['transfers'] else 'One change at '+j['transfer_stop']['name']+'. ')
    if shortest is j and fastest is not j:j['explanation']+=f"Shortest measured path; {round(j['total_minutes']-fastest['total_minutes'],1)} min longer than the fastest result."
    elif fastest is j:j['explanation']+='Earliest estimated destination arrival among the searched paths.'
    else:j['explanation']+=f"{round(j['total_minutes']-fastest['total_minutes'],1)} min longer than the fastest result."
  return items,dict(patterns_in_network=len(self.g['patterns']),templates_searched=processed,trip_instances_evaluated=self.instances,limited=self.limited,max_templates=MAX_TEMPLATES,max_trip_instances=MAX_INSTANCES,max_results=MAX_RESULTS,max_transfers=self.max_transfers,departure_window_minutes=int((self.first_deadline-self.clock).total_seconds()/60),journey_limit_minutes=int((self.deadline-self.clock).total_seconds()/60),transfer_buffer_seconds=TRANSFER_SECONDS,transfer_policy='Same exact stop ID only; three-minute planning buffer, not a surveyed transfer guarantee. No walking links inferred.',distance_note='Distances follow ordered GTFS shapes where aligned; missing shapes are labelled stop-segment estimates. Shortest badge compares measured paths only.',scope='Best among bounded searched paths; not every possible Bengaluru journey.',elapsed_ms=round((time.monotonic()-self.started)*1000))

@router.get('/explore')
def explore(origin:str,destination:str,sort:SORTS='recommended',max_transfers:int=Query(1,ge=0,le=1),window_minutes:int=Query(120,ge=30,le=240),duration_minutes:int=Query(240,ge=30,le=360),limit:int=Query(10,ge=1,le=20),offset:int=Query(0,ge=0,le=80),depart_at:datetime|None=None,search_id:str|None=Query(None,max_length=40)):
 from . import main
 main.stop(origin);main.stop(destination)
 if origin==destination:raise HTTPException(422,'Choose two different stops.')
 now=datetime.now(TZ)
 if depart_at is not None and (depart_at.tzinfo is None or not now-timedelta(minutes=1)<=depart_at<=now+timedelta(days=30)):raise HTTPException(422,'Use a timezone-aware departure between now and 30 days ahead.')
 params=(origin,destination,max_transfers,window_minutes,duration_minutes,depart_at.isoformat() if depart_at else None,version(),feeds.mode(),feeds.source_id())
 with LOCK:
  for key in list(SNAPSHOTS):
   if SNAPSHOTS[key]['expires']<time.monotonic():del SNAPSHOTS[key]
  if search_id:
   snapshot=SNAPSHOTS.get(search_id)
   if not snapshot or snapshot['params']!=params:raise HTTPException(409,'Search snapshot expired or context changed. Search again.')
  else:snapshot=None
 if snapshot is None:
  if offset:raise HTTPException(422,'Load more requires the search_id from the first page.')
  clock=depart_at.astimezone(TZ) if depart_at else now
  if not SEARCH_SLOTS.acquire(blocking=False):raise HTTPException(503,'Route search is busy. Please retry in a few seconds.')
  search=None
  try:
   search=Search(origin,destination,clock,window_minutes,duration_minutes,max_transfers)
   items,coverage=search.run()
  finally:
   if search:search.close()
   SEARCH_SLOTS.release()
  search_id=uuid.uuid4().hex;snapshot=dict(params=params,items=items,coverage=coverage,clock=clock.isoformat(),generated_at=now.isoformat(),expires=time.monotonic()+120)
  with LOCK:
   if len(SNAPSHOTS)>=20:del SNAPSHOTS[next(iter(SNAPSHOTS))]
   SNAPSHOTS[search_id]=snapshot
 items=snapshot['items']
 keys={'recommended':lambda j:(j['score'],j['id']),'comfortable':lambda j:(j['score'],j['id']),'fastest':lambda j:(j['total_minutes'],j['transfers'],j['id']),'shortest':lambda j:(not j['distance_measured'],j['distance_km'],j['total_minutes'],j['id']),'fewest_transfers':lambda j:(j['transfers'],j['total_minutes'],j['id'])}
 ordered=sorted(items,key=keys[sort]);page=ordered[offset:offset+limit]
 return dict(journeys=page,total=len(items),search_id=search_id,generated_at=snapshot['generated_at'],departure_at=snapshot['clock'],sort=sort,offset=offset,next_offset=offset+len(page),has_more=offset+len(page)<len(items),coverage=snapshot['coverage'])
