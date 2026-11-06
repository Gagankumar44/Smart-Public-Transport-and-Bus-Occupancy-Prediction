"""Shared method selection, simulated demand and honest heuristic uncertainty."""
from datetime import timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router=APIRouter(prefix='/api')
DEMAND_PROFILES={'morning':1.0,'afternoon':.7,'evening':1.2,'low':.4}

def select_eta(*,mode,scheduled_remaining,progress_remaining=None,observation_age=None,history_remaining=None):
 fresh=observation_age is not None and observation_age<=120 and progress_remaining is not None
 if mode=='simulation' and fresh:return progress_remaining,'simulation_progress','simulation'
 if mode!='simulation' and fresh:
  if history_remaining is not None:return .7*progress_remaining+.3*history_remaining,'history_adjusted_progress','historical'
  return progress_remaining,'vehicle_progress','real_observed'
 if mode!='simulation' and history_remaining is not None:return history_remaining,'historical_segments','historical'
 return scheduled_remaining,'scheduled_baseline','schedule'

def uncertainty(remaining,stops_ahead,age,scenario,conflict=False):
 # Design bounds only. No empirical calibration is implied.
 spread=max(60,remaining*.12)+max(0,stops_ahead)*8+min(age,900)*.3
 if scenario=='traffic':spread*=1.5
 if conflict:spread*=1.3
 return dict(kind='heuristic',label='Scenario bounds, not a calibrated probability interval',
  lower_minutes=round(max(0,remaining-spread)/60,1),upper_minutes=round((remaining+spread)/60,1),
  occupancy_uncertainty='High' if conflict or age>120 or stops_ahead>7 else 'Moderate',
  stops_ahead=stops_ahead,observation_age_seconds=round(age,1),calibrated=False)

class ForecastPoint(BaseModel):
 stop_id:str
 stop_name:str
 arrival_at:str
 minutes:float
 crowding:str
 utilization:float|None
 method:str
 metadata:dict
 uncertainty:dict

@router.get('/vehicles/{vid}/forecast',response_model=list[ForecastPoint])
def future_forecast(vid:str):
 from . import main as m
 elapsed,now,vehicles=m.snapshot();v=next((v for v in vehicles if v['id']==vid),None)
 if not v:v=m.get_vehicle(vid)
 points=[]
 for sid in (v['record']['logical_route']['stops'] if v.get('external') else m.route(v['route_id'])['stops']):
  p=m.prediction(v,sid,elapsed,now)
  if p:points.append(dict(stop_id=sid,stop_name=m.stop(sid)['name'],arrival_at=p['arrival_at'],minutes=p['minutes'],crowding=p['crowding'],utilization=p['utilization'],method=p['metadata']['method'],metadata=p['metadata'],uncertainty=p['uncertainty']))
 return points

@router.get('/predictions/methods')
def methods():
 from .feeds import mode
 return dict(active='simulation_progress' if mode()=='simulation' else 'adapter_selected',ml_enabled=False,
  selection=['Fresh simulated observation → simulation progress with segment travel and dwell',
   'Fresh genuine observation → progress; optionally blend genuine historical segment data',
   'Stale/missing observation → historical genuine segments if available, otherwise schedule'],
  uncertainty='Heuristic scenario bounds, not statistically calibrated',
  demand_profiles=DEMAND_PROFILES,
  note='Source adapters are available; consult Data Health for verified connectivity. Offline CSV imports never automatically replace current observations or activate historical serving.')

@router.get('/data/quality')
def data_quality():
 from .history import dataset_summary
 return dataset_summary()

@router.get('/insights/prediction-quality')
def prediction_quality():
 from .history import quality_summary
 from .ground_truth import latest_evaluation,calibration_status
 result=quality_summary();result['simulation']=None;result['imported_unverified']=result.get('real');result['real']=latest_evaluation();result['calibration']=calibration_status()
 result['message']=result['real']['message'] if result['real'] else 'Insufficient verified real-world observations for reliable evaluation.'
 return result
