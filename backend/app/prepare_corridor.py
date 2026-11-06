"""Extract an inspectable, attributed real stop sequence for the demo corridor."""
import json
import zipfile
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
def prepare(path):
 with zipfile.ZipFile(path) as z:
  stops=pd.read_csv(z.open('stops.txt'),dtype=str).fillna('')
  times=pd.read_csv(z.open('stop_times.txt'),dtype=str)
  trips=pd.read_csv(z.open('trips.txt'),dtype=str)
  routes=pd.read_csv(z.open('routes.txt'),dtype=str)
  candidates=trips.merge(routes,on='route_id')
  candidates=candidates[candidates.route_short_name=='500-F']
  chosen=None
  for _,trip in candidates.iterrows():
   seq=times[times.trip_id==trip.trip_id].copy()
   seq['order']=seq.stop_sequence.astype(int);seq=seq.sort_values('order')
   ids=list(seq.stop_id)
   if '20707' in ids and '22670' in ids and ids.index('20707')<ids.index('22670'):
    chosen=seq.iloc[ids.index('20707'):ids.index('22670')+1];break
  if chosen is None: raise ValueError('No validated outbound corridor found')
  output=[]
  for _,record in chosen.iterrows():
   s=stops[stops.stop_id==record.stop_id].iloc[0]
   output.append(dict(id={'20707':'silk','22670':'marathahalli'}.get(s.stop_id,s.stop_id),name=s.stop_name,
    lat=float(s.stop_lat),lon=float(s.stop_lon),context=s.stop_desc or 'Bengaluru · BMTC GTFS',gtfs_stop_id=s.stop_id))
  result=dict(stops=output,route_reference='500-F',trip_reference=trip.trip_id,
   source='https://github.com/Vonter/bmtc-gtfs',license='ODbL-1.0; individual contents may be copyright BMTC',
   notice='Actual stop sequence from GTFS. All demo departures, vehicles, reverse patterns and occupancy are synthetic. Lines connect stops, not road geometry.')
  (ROOT/'data/corridor.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
  print(f'Extracted {len(output)} stops from GTFS route 500-F')
if __name__=='__main__': prepare(ROOT/'data/bmtc.zip')
