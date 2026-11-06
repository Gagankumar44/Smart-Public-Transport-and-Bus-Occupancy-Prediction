import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ['RUSHLESS_TEST_MODE']='true'
os.environ['RUSHLESS_DATA_MODE']='simulation'
import pytest
from sqlalchemy import create_engine,text
@pytest.fixture(autouse=True)
def isolate_runtime_databases(tmp_path,monkeypatch):
 from app import main,pilot_store,history,intelligence
 engine=create_engine('sqlite:///'+str(tmp_path/'runtime.db'))
 monkeypatch.setattr(main,'engine',engine)
 monkeypatch.setattr(pilot_store,'DB_PATH',tmp_path/'profiles.db')
 monkeypatch.setattr(history,'DB_PATH',tmp_path/'history.db')
 with engine.begin() as db:
  db.execute(text('CREATE TABLE stops(id TEXT PRIMARY KEY,name TEXT,lat REAL,lon REAL)'))
  db.execute(text('CREATE TABLE scenario_events(at TEXT,scenario TEXT)'))
  db.execute(text('INSERT INTO stops VALUES (:id,:name,:lat,:lon)'),main.STOPS)
 intelligence.init_db()
 yield
 engine.dispose()
