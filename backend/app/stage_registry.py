"""Stage a corridor's real GTFS records without replacing any existing database."""
import argparse
import json
import sqlite3
import zipfile
from pathlib import Path
import pandas as pd

def stage(path,output,route_name='500-F'):
 output=Path(output)
 if output.exists():raise ValueError('Output already exists; choose a new registry path to preserve existing data')
 with zipfile.ZipFile(path) as z:
  routes=pd.read_csv(z.open('routes.txt'),dtype=str).fillna('');routes=routes[routes.route_short_name==route_name]
  if routes.empty:raise ValueError('Route short name not found in this dataset')
  trips=pd.read_csv(z.open('trips.txt'),dtype=str).fillna('');trips=trips[trips.route_id.isin(routes.route_id)]
  times=pd.read_csv(z.open('stop_times.txt'),dtype=str).fillna('');times=times[times.trip_id.isin(trips.trip_id)]
  stops=pd.read_csv(z.open('stops.txt'),dtype=str).fillna('');stops=stops[stops.stop_id.isin(times.stop_id)]
  with sqlite3.connect(output) as db:
   db.execute('CREATE TABLE rushless_registry_metadata(synthetic INTEGER)');db.execute('INSERT INTO rushless_registry_metadata VALUES (0)')
   for name,frame in [('routes',routes),('trips',trips),('stop_times',times),('stops',stops)]:frame.to_sql(name,db,index=False)
   for name in ['calendar','calendar_dates']:
    if name+'.txt' in z.namelist():pd.read_csv(z.open(name+'.txt'),dtype=str).fillna('').to_sql(name,db,index=False)
   db.execute('CREATE INDEX trip_lookup ON trips(trip_id)');db.execute('CREATE INDEX time_lookup ON stop_times(trip_id,stop_id)')
 return dict(routes=len(routes),trips=len(trips),stops=len(stops),output=str(output),note='Staged GTFS schedule registry only; no live provider connected. Shapes omitted; matching uses supported corridor stop geometry.')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('zip');p.add_argument('--output',required=True);p.add_argument('--route',default='500-F');a=p.parse_args()
 try:print(json.dumps(stage(a.zip,a.output,a.route)))
 except ValueError as e:p.exit(2,str(e)+'\n')
