"""Remove known synthetic runtime records; retain private recovery snapshots."""
import json,sqlite3
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
def clean():
 backup=ROOT/'data/private'/('removed-demo-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
 backup.mkdir(parents=True,exist_ok=False);counts={}
 for name in ['pilot.db','observations.db','rushless.db']:
  path=ROOT/'data'/name
  if not path.exists():continue
  with sqlite3.connect(path) as db:
   recovery=sqlite3.connect(backup/name);db.backup(recovery);recovery.close()
   tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
   if name=='pilot.db':
    ids=[r[0] for r in db.execute("SELECT id FROM sources WHERE synthetic=1 OR mode='simulation'")]
    for sid in ids:
     for table in ['transport_observations','raw_feeds','provider_attempts']:db.execute('DELETE FROM '+table+' WHERE source_id=?',(sid,))
     db.execute('DELETE FROM sources WHERE id=?',(sid,))
    counts['synthetic_sources']=len(ids)
    counts['practice_observations']=db.execute("DELETE FROM pilot_observations WHERE source_type IN ('simulation','replay_synthetic')").rowcount
    db.execute("DELETE FROM forecasts WHERE source_mode IN ('simulation','replay_synthetic')")
    removed=0
    for token,data in db.execute('SELECT token_hash,data FROM commuter_profiles').fetchall():
     profile=json.loads(data);before=len(profile.get('saved',[]));profile['saved']=[j for j in profile.get('saved',[]) if 'demo' not in j['name'].lower() and 'hackathon' not in j['name'].lower()];removed+=before-len(profile['saved']);db.execute('UPDATE commuter_profiles SET data=? WHERE token_hash=?',(json.dumps(profile),token))
    counts['demo_named_saved_pairs']=removed
   elif name=='observations.db':
    ids=[r[0] for r in db.execute('SELECT id,metadata FROM datasets') if json.loads(r[1]).get('mode')=='simulation']
    for ident in ids:
     for (eid,) in db.execute('SELECT id FROM evaluations WHERE dataset_id=?',(ident,)).fetchall():db.execute('DELETE FROM prediction_outputs WHERE evaluation_id=?',(eid,))
     for table in ['observations','features','evaluations']:db.execute('DELETE FROM '+table+' WHERE dataset_id=?',(ident,))
     db.execute('DELETE FROM datasets WHERE id=?',(ident,))
    counts['synthetic_datasets']=len(ids)
   else:
    for table in ['scenario_events','crowd_reports']:
     if table in tables:counts[table]=db.execute('DELETE FROM '+table).rowcount
 print(json.dumps(counts,indent=2))
if __name__=='__main__':clean()
