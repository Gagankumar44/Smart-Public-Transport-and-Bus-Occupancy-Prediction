"""Opt-in local authorized feed worker; Ctrl+C stops polling. Never started by the web API."""
import argparse,time,os
from .feeds import fetch_configured

def poll(cycles=0,fetch=fetch_configured,wait=time.sleep):
 interval=max(15,int(os.getenv('TRANSIT_POLL_SECONDS','60')));failures=0;count=0
 while cycles==0 or count<cycles:
  try:fetch();failures=0;print('Authorized feed poll completed',flush=True)
  except ValueError:failures+=1;print('Feed unavailable; retrying with backoff. No live connection claimed.',flush=True)
  count+=1
  if cycles==0 or count<cycles:wait(min(900,interval*2**min(failures,4)))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--cycles',type=int,default=0);a=p.parse_args()
 if a.cycles<0:p.error('cycles must be nonnegative')
 try:poll(a.cycles)
 except KeyboardInterrupt:print('Polling stopped')
