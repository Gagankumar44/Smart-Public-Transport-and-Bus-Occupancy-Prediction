"""GTFS schedule lookup against a staged import, including service exceptions."""
import sqlite3
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Asia/Kolkata')
def service_active(db,service_id,service_date):
 date=service_date.strftime('%Y%m%d')
 tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 if 'calendar_dates' in tables:
  exception=db.execute('SELECT exception_type FROM calendar_dates WHERE service_id=? AND date=?',(service_id,date)).fetchone()
  if exception:return str(exception[0])=='1'
 if 'calendar' not in tables:return False
 db.row_factory=sqlite3.Row
 row=db.execute('SELECT * FROM calendar WHERE service_id=?',(service_id,)).fetchone()
 return bool(row and row['start_date']<=date<=row['end_date'] and str(row[service_date.strftime('%A').lower()])=='1')

def scheduled_arrival(path,trip_id,stop_id,service_date):
 from .import_gtfs import seconds
 day=datetime.strptime(service_date,'%Y-%m-%d').replace(tzinfo=TZ)
 with sqlite3.connect(path) as db:
  row=db.execute('SELECT service_id FROM trips WHERE trip_id=?',(trip_id,)).fetchone()
  if not row:raise ValueError('Unknown trip')
  if not service_active(db,row[0],day):raise ValueError('Trip is not active on the requested service date')
  row=db.execute('SELECT arrival_time FROM stop_times WHERE trip_id=? AND stop_id=? ORDER BY CAST(stop_sequence AS INTEGER)',(trip_id,stop_id)).fetchone()
  if not row or not row[0]:raise ValueError('No scheduled arrival at this stop')
  return day+timedelta(seconds=seconds(row[0]))
