"""Opt-in, isolated visualization of the existing Simulation/vehicle engine.

Never changes serving mode, real observations, main simulation or journey watches.
"""
import bisect,math,threading,time
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel
from . import main,network,feeds
from .predictive import select_eta

router=APIRouter(prefix='/api/tracking/demo-preview')
LOCK=threading.RLock();simulation=main.Simulation();simulation.started-=420
paused=False;pause_elapsed=0.

def geometry():
 ids=main.ROUTES[0]['stops']
 for r in network.patterns('500-F',80):
  if all(s in r['stops'] for s in ids) and [r['stops'].index(s) for s in ids]==sorted(r['stops'].index(s) for s in ids):
   points=network.geometry(r['trip_id'],main.stop(ids[0]),main.stop(ids[-1]))
   if points:
    cursor=0;indices=[]
    for sid in ids:
     stop=main.stop(sid);cursor=min(range(cursor,len(points)),key=lambda i:feeds.distance((stop['lat'],stop['lon']),points[i]));indices.append(cursor)
    cumulative=[0.]
    for a,b in zip(points,points[1:]):cumulative.append(cumulative[-1]+feeds.distance(a,b))
    if cumulative[-1]>0:return points,indices,cumulative,'Published GTFS shape; simulated vehicle'
 points=[[main.stop(s)['lat'],main.stop(s)['lon']] for s in ids];cumulative=[0.]
 for a,b in zip(points,points[1:]):cumulative.append(cumulative[-1]+feeds.distance(a,b))
 return points,list(range(len(points))),cumulative,'Stop-segment demo geometry; not a verified road path'

_geometry_key=None;_geometry=None
def snapshot():
 global _geometry,_geometry_key
 with LOCK:
  elapsed,clock=simulation.state()
  if paused:elapsed=pause_elapsed;clock=simulation.epoch+timedelta(seconds=elapsed)
  r=main.ROUTES[0];v=main.vehicle(r,0,elapsed,clock,simulation=simulation)
  key=(str(network.active_path()),network.active_path().stat().st_mtime_ns)
  if _geometry_key!=key:_geometry=geometry();_geometry_key=key
  points,indices,cumulative,method=_geometry
  progress=max(0,min(len(r['stops'])-1,v['progress']));segment=min(len(indices)-2,int(progress));fraction=progress-segment
  distance=cumulative[indices[segment]]+(cumulative[indices[segment+1]]-cumulative[indices[segment]])*fraction
  point=min(len(points)-2,max(0,bisect.bisect_right(cumulative,distance)-1));span=cumulative[point+1]-cumulative[point];f=(distance-cumulative[point])/span if span else 0
  v['lat']=points[point][0]+(points[point+1][0]-points[point][0])*f;v['lon']=points[point][1]+(points[point+1][1]-points[point][1])*f
  v['paused']=paused;v['metadata']['reason']='Explicit demo preview, not live BMTC GPS.'
  next_index=min(len(r['stops'])-1,max(0,math.floor(v['progress'])+1))
  remaining=max(0,v['start_seconds']-elapsed)+(next_index-max(0,v['progress']))*v['segment_seconds']
  remaining,_,_=select_eta(mode='simulation',scheduled_remaining=remaining,progress_remaining=remaining,observation_age=0)
  return dict(mode='simulation_preview',source='simulation',live_connected=False,paused=paused,clock=clock.isoformat(),generation=simulation.generation,vehicle=v,geometry=points,geometry_source=method,stops=[main.stop(s) for s in r['stops']],next_stop=main.stop(r['stops'][next_index]),next_stop_minutes=None if v['completed'] else round(max(0,remaining)/60,1),note='Synthetic preview using the existing simulation engine. Positions, passenger counts and ETA are simulated. Production data mode is unchanged.')

class Control(BaseModel):
 action:Literal['pause','resume','restart']

@router.get('')
def read_preview():return snapshot()

@router.post('')
def control(body:Control):
 global paused,pause_elapsed
 with LOCK:
  if body.action=='pause' and not paused:pause_elapsed=simulation.state()[0];paused=True
  if body.action=='resume' and paused:simulation.started=time.monotonic()-pause_elapsed;paused=False
  if body.action=='restart':simulation.reset('normal');simulation.started-=420;paused=False
  return snapshot()
