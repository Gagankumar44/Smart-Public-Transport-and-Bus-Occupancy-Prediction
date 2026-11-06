"""Scoped GTFS-RT disruptions. Text never invents an ETA or a replacement route."""
from google.transit import gtfs_realtime_pb2 as gtfs
from . import feeds
from .history import instant

BLOCKING={gtfs.Alert.NO_SERVICE,gtfs.Alert.DETOUR,gtfs.Alert.STOP_MOVED}

def active_alerts(clock):
 source,records=feeds.current_records()
 if not source:return []
 return [r for r in records if r['kind']=='service_alert' and 0<=(clock-instant(r['observed_at'])).total_seconds()<=120 and (not r['active_periods'] or any(p.get('start',0)<=clock.timestamp()<p.get('end',253402300799) for p in r['active_periods']))]

def selector_matches(selector,info,service_date,stop_ids):
 """Fields inside a selector are AND; different selectors are OR."""
 route=info['route'];trip=info['trip']
 checks={'agency_id':route.get('agency_id'),'route_id':route['route_id'],'route_type':route.get('route_type'),'direction_id':trip.get('direction_id')}
 for field,value in checks.items():
  if field in selector and str(selector[field])!=str(value):return False
 if 'stop_id' in selector and selector['stop_id'] not in stop_ids:return False
 for field,value in selector.get('trip',{}).items():
  expected={'trip_id':trip['trip_id'],'route_id':route['route_id'],'direction_id':trip.get('direction_id'),'start_date':service_date,'start_time':info['origin_time']}.get(field)
  if str(value)!=str(expected):return False
 return bool(selector)

def for_journey(v,origin,destination,clock,alerts=None,*,origin_index=None,destination_index=None):
 if not v.get('external'):return []
 info=feeds.trip_info(v['trip_id'])
 if not info:return []
 times=info['times'];ids=[t['id'] for t in times]
 if origin not in ids or destination not in ids:return []
 x=ids.index(origin) if origin_index is None else origin_index
 y=ids.index(destination) if destination_index is None else destination_index
 if not 0<=x<len(times) or not 0<=y<len(times) or ids[x]!=origin or ids[y]!=destination:return []
 result=[]
 update=v.get('update') or (v['record'] if v['record'].get('cancelled') else None)
 if update and 0<=(clock-instant(update['observed_at'])).total_seconds()<=120:
  if update.get('cancelled'):result.append(dict(id='cancelled:'+v['trip_id'],kind='cancelled',message='Provider reports this trip cancelled. Its scheduled arrival is unavailable.',blocking=True))
  for u in update.get('updates',[]):
   if u['relationship']==gtfs.TripUpdate.StopTimeUpdate.SKIPPED and any((u['stop_sequence']==times[i]['sequence'] if u['stop_sequence'] is not None else u['stop_id']==times[i]['stop_id']) for i in [x,y]):
    result.append(dict(id='skipped:'+v['trip_id']+':'+str(u['stop_sequence'] or u['stop_id']),kind='skipped_stop',message='Provider reports the boarding or destination stop skipped. Choose another departure.',blocking=True))
 for alert in (active_alerts(clock) if alerts is None else alerts):
  affected=[times[i]['stop_id'] for i in range(x,y+1)] if alert['effect']==gtfs.Alert.DETOUR else [times[x]['stop_id'],times[y]['stop_id']]
  if any(selector_matches(s,info,v['service_date'],affected) for s in alert['selectors']):
   effect=gtfs.Alert.Effect.Name(alert['effect']).replace('_',' ').lower()
   result.append(dict(id=alert['entity_id'],kind='service_alert',message=' / '.join(alert['header']) or 'Provider service alert: '+effect,description=' / '.join(alert['description']),effect=effect,blocking=alert['effect'] in BLOCKING))
 return result
