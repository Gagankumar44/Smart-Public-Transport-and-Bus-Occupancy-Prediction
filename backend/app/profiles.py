"""Anonymous, server-side commuter settings. Cookie values are random capabilities."""
import hashlib
import json
import os
import secrets
import threading
from functools import wraps
from datetime import timedelta
from fastapi import APIRouter,HTTPException,Request,Response
from pydantic import BaseModel,Field
from typing import Literal
from . import pilot_store as store

router=APIRouter(prefix='/api/profile')
COOKIE='rushless_commuter'
PROFILE_LOCK=threading.RLock()
def serialized(fn):
 @wraps(fn)
 def invoke(*args,**kwargs):
  with PROFILE_LOCK:return fn(*args,**kwargs)
 return invoke
def default():return dict(preference='comfortable',alerts_enabled=True,saved=[],recent=[],last_context=None)
def profile(request,response):
 token=request.cookies.get(COOKIE,'');digest=hashlib.sha256(token.encode()).hexdigest();cutoff=(store.now()-timedelta(days=int(os.getenv('PROFILE_RETENTION_DAYS','30')))).isoformat()
 with store.connect() as db:
  db.execute('DELETE FROM commuter_profiles WHERE last_seen<?',(cutoff,))
  row=db.execute('SELECT data FROM commuter_profiles WHERE token_hash=?',(digest,)).fetchone() if len(token)==64 else None
  if not row:
   token=secrets.token_hex(32);digest=hashlib.sha256(token.encode()).hexdigest();data=default()
   db.execute('INSERT INTO commuter_profiles VALUES (?,?,?,?)',(digest,store.stamp(),store.stamp(),store.json_value(data)))
  else:data=json.loads(row['data']);db.execute('UPDATE commuter_profiles SET last_seen=? WHERE token_hash=?',(store.stamp(),digest))
 response.set_cookie(COOKIE,token,httponly=True,secure=request.url.scheme=='https' or os.getenv('COOKIE_SECURE','false').lower()=='true',samesite='strict',max_age=int(os.getenv('PROFILE_RETENTION_DAYS','30'))*86400,path='/')
 return digest,data
def save(identity,data):
 with store.connect() as db:db.execute('UPDATE commuter_profiles SET data=? WHERE token_hash=?',(store.json_value(data),identity))
def validate_pair(origin,destination):
 from . import main as m
 m.stop(origin);m.stop(destination)
 if origin==destination:raise HTTPException(422,'Choose two different stops.')

class Preferences(BaseModel):
 preference:Literal['fastest','comfortable']|None=None
 alerts_enabled:bool|None=None
class Pair(BaseModel):
 origin:str=Field(max_length=100)
 destination:str=Field(max_length=100)
class Saved(Pair):
 model_config={'str_strip_whitespace':True}
 name:str=Field(min_length=1,max_length=60)
class Rename(BaseModel):
 model_config={'str_strip_whitespace':True}
 name:str=Field(min_length=1,max_length=60)

@router.get('')
@serialized
def get_profile(request:Request,response:Response):return profile(request,response)[1]
@router.patch('/preferences')
@serialized
def preferences(body:Preferences,request:Request,response:Response):
 identity,data=profile(request,response);data.update(body.model_dump(exclude_none=True));save(identity,data);return data
@router.post('/saved-journeys',status_code=201)
@serialized
def save_journey(body:Saved,request:Request,response:Response):
 validate_pair(body.origin,body.destination);identity,data=profile(request,response)
 if len(data['saved'])>=12:raise HTTPException(409,'You can save up to 12 journeys.')
 item=dict(id=secrets.token_hex(12),**body.model_dump());data['saved'].append(item);save(identity,data);return data
@router.patch('/saved-journeys/{sid}')
@serialized
def rename(sid:str,body:Rename,request:Request,response:Response):
 identity,data=profile(request,response);item=next((j for j in data['saved'] if j['id']==sid),None)
 if not item:raise HTTPException(404,'Saved journey not found.')
 item['name']=body.name;save(identity,data);return data
@router.delete('/saved-journeys/{sid}')
@serialized
def remove(sid:str,request:Request,response:Response):
 identity,data=profile(request,response);data['saved']=[j for j in data['saved'] if j['id']!=sid];save(identity,data);return data
@router.post('/recent')
@serialized
def recent(body:Pair,request:Request,response:Response):
 validate_pair(body.origin,body.destination);identity,data=profile(request,response);pair=body.model_dump()
 data['recent']=[pair]+[j for j in data['recent'] if j!=pair][:4];data['last_context']=pair;save(identity,data);return data
@router.delete('/recent')
@serialized
def clear_recent(request:Request,response:Response):
 identity,data=profile(request,response);data['recent']=[];data['last_context']=None;save(identity,data);return data
@router.delete('',status_code=204)
@serialized
def reset_profile(request:Request,response:Response):
 identity,_=profile(request,response)
 with store.connect() as db:db.execute('DELETE FROM commuter_profiles WHERE token_hash=?',(identity,))
 response.delete_cookie(COOKIE,path='/')
