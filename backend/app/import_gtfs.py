"""Validate and import a local GTFS ZIP into a separate SQLite database."""
import argparse
import sqlite3
import zipfile
from pathlib import Path
import pandas as pd

def seconds(value):
 h,m,s=map(int,str(value).split(':'))
 if h<0 or not 0<=m<60 or not 0<=s<60: raise ValueError('Invalid GTFS time')
 return h*3600+m*60+s

def import_feed(path,output):
 with zipfile.ZipFile(path) as archive, sqlite3.connect(output) as db:
  names={Path(n).name:n for n in archive.namelist()}
  for required in ['stops.txt','routes.txt','trips.txt','stop_times.txt']:
   if required not in names: raise ValueError(f'Missing {required}')
  if not {'calendar.txt','calendar_dates.txt'} & names.keys(): raise ValueError('Missing service calendar')
  for name in ['stops','routes','trips','stop_times','shapes','calendar','calendar_dates']:
   if name+'.txt' not in names: continue
   frame=pd.read_csv(archive.open(names[name+'.txt']),dtype=str).fillna('')
   if name=='stops':
    lat=pd.to_numeric(frame.stop_lat);lon=pd.to_numeric(frame.stop_lon)
    if not ((lat.between(12,14)) & (lon.between(77,78.5))).all(): raise ValueError('Stops outside Bengaluru region')
   if name=='stop_times':
    for field in ['arrival_time','departure_time']:
     frame[field+'_seconds']=frame[field].map(lambda t:seconds(t) if t else None)
   frame.to_sql(name,db,if_exists='replace',index=False)
 return str(output)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('zip');parser.add_argument('--output',default='data/gtfs.db')
 args=parser.parse_args();print(import_feed(args.zip,args.output))
