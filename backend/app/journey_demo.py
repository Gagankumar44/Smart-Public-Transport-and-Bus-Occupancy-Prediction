"""Explicit illustrative fallback; never observations or published bus services."""
from datetime import timedelta
from types import SimpleNamespace

def paths(origin,destination,clock):
 from .explorer import Search,haversine
 km=haversine([origin['lat'],origin['lon']],[destination['lat'],destination['lon']])
 results=[]
 for i,speed in enumerate([18,24,15]):
  wait=[5,12,3][i];ride=round(max(4,km/speed*60),1)
  board=clock+timedelta(minutes=wait);arrival=board+timedelta(minutes=ride)
  ident=f"demo-connection:{origin['id']}:{destination['id']}:{i}"
  meta=dict(source='demo_journey',method='Illustrative straight-line travel model',confidence='Low',observed_at=clock.isoformat(),generated_at=clock.isoformat(),generation='demo-connection',reason='Synthetic example, not a verified BMTC service or live ETA.',evidence='No passenger or GPS observations',uncertainty=None)
  stops=[{**origin,'arrival_at':board.isoformat()},{**destination,'arrival_at':arrival.isoformat()}]
  leg=dict(id=ident,trip_id=ident,service_date=clock.strftime('%Y%m%d'),route_id=ident,route_name=f'DEMO connection {i+1}',vehicle_id=ident,origin=origin,destination=destination,boarding_at=board.isoformat(),arrival_at=arrival.isoformat(),ride_minutes=ride,wait_minutes=wait,total_minutes=wait+ride,stop_count=1,stops=stops,crowding='Unknown',utilization=None,metadata=meta,distance_km=round(km,3),geometry=[[s['lat'],s['lon']] for s in stops],distance_method='Illustrative straight-line estimate; not a road route',measured=False)
  path=Search.build(SimpleNamespace(clock=clock,first_deadline=clock+timedelta(hours=2)),[leg])
  path['badges']=['DEMO · not a real bus service'];path['explanation']='Illustrative connection because this search found no supported timetable journey. Straight-line map only; times are synthetic.'
  results.append(path)
 return results
