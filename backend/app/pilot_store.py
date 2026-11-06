"""Additive, private Phase 4 storage. Provider secrets never enter this database."""
import json
import os
import sqlite3
from datetime import datetime,timezone
from pathlib import Path

DB_PATH=Path(__file__).resolve().parents[2]/'data/pilot.db'
def now():return datetime.now(timezone.utc)
def stamp():return now().isoformat()
def connect():
 db=sqlite3.connect(DB_PATH,timeout=10);db.row_factory=sqlite3.Row
 db.executescript('''
 CREATE TABLE IF NOT EXISTS pilot_schema(version INTEGER PRIMARY KEY);INSERT OR IGNORE INTO pilot_schema VALUES(1);
 CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, mode TEXT, provenance TEXT, license TEXT, synthetic INTEGER, status TEXT, last_success TEXT, error TEXT);
 CREATE TABLE IF NOT EXISTS raw_feeds(id TEXT PRIMARY KEY, source_id TEXT, received_at TEXT, payload BLOB, status TEXT);
 CREATE TABLE IF NOT EXISTS provider_attempts(source_id TEXT PRIMARY KEY, last_attempt TEXT);
 CREATE TABLE IF NOT EXISTS source_snapshots(source_id TEXT PRIMARY KEY, feed_timestamp INTEGER, observation_ids TEXT);
 CREATE TABLE IF NOT EXISTS transport_observations(id TEXT PRIMARY KEY, source_id TEXT, vehicle_id TEXT, trip_id TEXT, service_date TEXT, observed_at TEXT, kind TEXT, status TEXT, payload TEXT);
 CREATE INDEX IF NOT EXISTS transport_latest ON transport_observations(source_id,vehicle_id,observed_at);
 CREATE TABLE IF NOT EXISTS pilot_observations(id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, kind TEXT, submitted_at TEXT, event_at TEXT, source_type TEXT, status TEXT, raw TEXT, normalized TEXT, review TEXT);
 CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY, created_at TEXT, source_id TEXT, source_mode TEXT, trip_id TEXT, service_date TEXT, stop_id TEXT, method TEXT, model_version TEXT, predicted_at TEXT, crowding TEXT, payload TEXT);
 CREATE INDEX IF NOT EXISTS forecast_event ON forecasts(source_id,trip_id,service_date,stop_id,created_at);
 CREATE TABLE IF NOT EXISTS pilot_evaluations(id TEXT PRIMARY KEY, created_at TEXT, payload TEXT);
 CREATE TABLE IF NOT EXISTS calibrations(id TEXT PRIMARY KEY, created_at TEXT, payload TEXT, active INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS commuter_profiles(token_hash TEXT PRIMARY KEY, created_at TEXT, last_seen TEXT, data TEXT);
 CREATE TABLE IF NOT EXISTS verified_exports(sha256 TEXT PRIMARY KEY, created_at TEXT, provenance TEXT);
 ''')
 return db
def json_value(value):return json.dumps(value,separators=(',',':'),sort_keys=True)
