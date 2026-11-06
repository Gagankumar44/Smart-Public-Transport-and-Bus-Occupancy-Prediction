"""Route monitor: fresh observations and static timetables remain distinct."""
import math
from . import feeds
from .history import instant

def positioned(vehicle,clock):
 record=vehicle.get('record',{})
 return bool(not vehicle['completed'] and record.get('kind')=='vehicle_position' and record.get('status')=='accepted' and 0<=(clock-instant(record['observed_at'])).total_seconds()<=120 and all(isinstance(vehicle.get(k),(int,float)) and math.isfinite(vehicle[k]) for k in ['lat','lon']))

def route_monitor(rid,stop_index,limit):
 from . import main,network
 from .disruptions import active_alerts,for_journey
 from fastapi import HTTPException
 route=main.route(rid)
 if stop_index>=len(route['stops']):raise HTTPException(422,'Select a stop on this route pattern.')
 sid=route['stops'][stop_index];elapsed,clock,fleet=main.snapshot()
 source,_=feeds.current_records()
 live=bool(feeds.mode()=='authorized' and source and source['mode']=='authorized' and not source['synthetic'])
 route_fleet=[v for v in fleet if v['route_id']==rid]
 observations=[]
 for v in route_fleet:
  if not positioned(v,clock):continue
  p=v['record'];speed=p.get('speed_mps')
  movement='moving' if speed is not None and speed>.5 else 'stopped' if speed is not None or p.get('stopped') else 'unknown'
  observations.append({**{k:v.get(k) for k in ['id','trip_id','route_id','route_name','lat','lon','next_stop','passengers','capacity','completed','metadata']},'movement':movement,'speed_kmh':round(speed*3.6,1) if speed is not None else None,'bearing':p.get('bearing')})
 alerts=active_alerts(clock);predictions=[];excluded=set()
 for v in route_fleet:
  if not v.get('external'):continue
  fresh=any(p and p.get('kind') in ['vehicle_position','trip_update'] and 0<=(clock-instant(p['observed_at'])).total_seconds()<=120 for p in [v['record'],v.get('update')])
  if not fresh:continue
  excluded.add((v['trip_id'],v['service_date']))
  if any(d['blocking'] for d in for_journey(v,sid,sid,clock,alerts,origin_index=stop_index,destination_index=stop_index)):continue
  prediction=feeds.external_prediction(v,sid,elapsed,clock,target_index=stop_index)
  if prediction:predictions.append(prediction)
 scheduled=network.departures(rid,clock,limit=20,stop_index=stop_index) or []
 for d in scheduled:
  if (d['trip_id'],d['service_date']) in excluded:continue
  v=feeds.scheduled_trip_vehicle(d['trip_id'],d['service_date'],clock)
  if not v or any(a['blocking'] for a in for_journey(v,sid,sid,clock,alerts,origin_index=stop_index,destination_index=stop_index)):continue
  prediction=feeds.external_prediction(v,sid,elapsed,clock,target_index=stop_index)
  if prediction:predictions.append(prediction)
 predictions.sort(key=lambda p:p['arrival_at'])
 return dict(route_id=rid,route_name=route['name'],stop=main.stop(sid),stop_index=stop_index,generated_at=clock.isoformat(),mode=feeds.mode(),live_connected=live and bool(observations),positioned_buses=len(observations),moving_buses=sum(v['movement']=='moving' for v in observations) if live and observations else None,stationary_buses=sum(v['movement']=='stopped' for v in observations) if live and observations else None,movement_unknown=sum(v['movement']=='unknown' for v in observations) if live and observations else None,vehicles=observations,arrivals=predictions[:limit],note='Counts cover fresh matched GPS observations on this directional pattern, not the whole BMTC fleet.' if live and observations else 'No fresh authorized GPS positions on this pattern. Moving-bus count and live location are unavailable; timetable estimates are shown separately.')
