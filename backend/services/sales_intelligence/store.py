"""Additive private SQLite archive, separate from native catalog and authored ledger."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock

SCHEMA = 5
INITIALIZE_LOCK = RLock()


def migrate(con, script):
    # Caller owns BEGIN IMMEDIATE; executescript would commit that lock early.
    for statement in script.split(';'):
        if statement.strip() and statement.strip() not in ('BEGIN IMMEDIATE', 'COMMIT'):
            con.execute(statement)


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp needs a timezone')
    return result.astimezone(timezone.utc)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def root():
    from services.product_validation import db_path
    return Path(os.environ.get('SALES_INTELLIGENCE_ROOT') or db_path().parent / 'sales-intelligence').resolve()


@contextmanager
def database(write=False):
    directory = root()
    directory.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(directory / 'intelligence.sqlite', timeout=20)
    con.row_factory = sqlite3.Row
    try:
        with INITIALIZE_LOCK:
            if con.execute('PRAGMA journal_mode').fetchone()[0] != 'wal':
                con.execute('PRAGMA journal_mode=WAL')
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA synchronous=FULL')
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA:
                raise ValueError('Research archive belongs to a newer runtime; use a compatible release')
            if version < SCHEMA:
                con.execute('BEGIN IMMEDIATE')
                version = con.execute('PRAGMA user_version').fetchone()[0]
                if version > SCHEMA:
                    raise ValueError('Research archive belongs to a newer runtime')
            if version < 1:
                migrate(con, '''
                BEGIN IMMEDIATE;
                CREATE TABLE control(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE sources(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE artifacts(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,captured_at TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE observations(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,listing_id TEXT NOT NULL,
                  metric TEXT NOT NULL,basis TEXT NOT NULL,unit TEXT NOT NULL,available_at TEXT NOT NULL,
                  captured_at TEXT NOT NULL,period_start TEXT,period_end TEXT,artifact_id TEXT NOT NULL,
                  supersedes TEXT,payload TEXT NOT NULL,FOREIGN KEY(artifact_id) REFERENCES artifacts(id));
                CREATE INDEX observations_listing ON observations(listing_id,metric,available_at DESC);
                CREATE INDEX observations_source ON observations(source_id,available_at);
                CREATE INDEX observations_superseded ON observations(supersedes);
                CREATE TABLE metadata(id TEXT PRIMARY KEY,listing_id TEXT NOT NULL,captured_at TEXT NOT NULL,
                  available_at TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE INDEX metadata_asof ON metadata(listing_id,available_at DESC,captured_at DESC);
                CREATE TABLE jobs(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,status TEXT NOT NULL,
                  due_at TEXT NOT NULL,lease_until TEXT,attempts INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL,result TEXT);
                CREATE INDEX jobs_due ON jobs(status,due_at);
                CREATE TABLE quota_events(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,account_ref TEXT NOT NULL,
                  bucket TEXT NOT NULL,cost REAL NOT NULL,at TEXT NOT NULL,status TEXT NOT NULL);
                CREATE INDEX quota_bucket ON quota_events(source_id,account_ref,bucket);
                CREATE TABLE outcomes(id TEXT PRIMARY KEY,listing_id TEXT NOT NULL,shop TEXT NOT NULL,
                  period_start TEXT NOT NULL,period_end TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE panels(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE datasets(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE models(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE predictions(id TEXT PRIMARY KEY,listing_id TEXT NOT NULL,model_id TEXT NOT NULL,
                  as_of TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE INDEX predictions_listing ON predictions(listing_id,as_of DESC);
                CREATE TABLE snapshots(id TEXT PRIMARY KEY,listing_id TEXT NOT NULL,kind TEXT NOT NULL,
                  as_of TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE outbox(id TEXT PRIMARY KEY,opportunity_id TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE audit(id INTEGER PRIMARY KEY,at TEXT NOT NULL,event TEXT NOT NULL,payload TEXT NOT NULL);
                PRAGMA user_version=1;
                COMMIT;
                ''')
            if version < 2:
                migrate(con, '''
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS metadata_latest(listing_id TEXT PRIMARY KEY,id TEXT NOT NULL,
                  captured_at TEXT NOT NULL,available_at TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS metadata_latest_time ON metadata_latest(captured_at DESC,listing_id);
                CREATE INDEX IF NOT EXISTS metadata_capture ON metadata(listing_id,captured_at DESC,available_at DESC,id DESC);
                INSERT OR REPLACE INTO metadata_latest SELECT m.listing_id,m.id,m.captured_at,m.available_at,m.payload FROM metadata m
                  WHERE m.id=(SELECT n.id FROM metadata n WHERE n.listing_id=m.listing_id ORDER BY n.captured_at DESC,n.available_at DESC,n.id DESC LIMIT 1);
                PRAGMA user_version=2;
                COMMIT;
                ''')
            if version < 3:
                migrate(con, '''
                CREATE INDEX IF NOT EXISTS observations_metric_listing ON observations(metric,listing_id,captured_at);
                ALTER TABLE metadata_latest ADD COLUMN search_text TEXT NOT NULL DEFAULT '';
                UPDATE metadata_latest SET search_text=lower(listing_id||char(10)||coalesce(json_extract(payload,'$.title'),'')||char(10)||coalesce(json_extract(payload,'$.shop'),''));
                PRAGMA user_version=3;
                ''')
            if version < 4:
                migrate(con, '''
                CREATE INDEX IF NOT EXISTS metadata_count ON metadata((1));
                CREATE INDEX IF NOT EXISTS metadata_latest_type_shop ON metadata_latest(
                  coalesce(json_extract(payload,'$.product_type'),'unknown'),json_extract(payload,'$.shop_id'));
                CREATE INDEX IF NOT EXISTS metadata_latest_shop ON metadata_latest(json_extract(payload,'$.shop_id'));
                PRAGMA user_version=4;
                ''')
            if version < 5:
                migrate(con, '''
                CREATE TABLE IF NOT EXISTS estimator_tracking(listing_id TEXT PRIMARY KEY,added_at TEXT NOT NULL,pinned INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS estimator_evidence(id TEXT PRIMARY KEY,listing_id TEXT NOT NULL,captured_at TEXT NOT NULL,available_at TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS estimator_evidence_listing ON estimator_evidence(listing_id,captured_at DESC,available_at DESC);
                CREATE TABLE IF NOT EXISTS estimator_latest(listing_id TEXT PRIMARY KEY,as_of TEXT NOT NULL,payload TEXT NOT NULL);
                PRAGMA user_version=5;
                ''')
            con.commit()
        if write:
            con.execute('BEGIN IMMEDIATE')
        yield con
        if write:
            con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def audit(con, event, payload):
    con.execute('INSERT INTO audit(at,event,payload) VALUES(?,?,?)', (now().isoformat(), event, encoded(payload)))


def get_control(con, key, default=None):
    row = con.execute('SELECT value FROM control WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_control(con, key, value):
    con.execute('INSERT INTO control VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, encoded(value)))


def add_metadata(con, value):
    ident = digest(value)
    cursor = con.execute('INSERT OR IGNORE INTO metadata VALUES(?,?,?,?,?)',
                (ident, value['listing_id'], value['captured_at'], value['available_at'], encoded(value)))
    if cursor.rowcount:
        search = '\n'.join(str(value.get(k, '')) for k in ('listing_id', 'title', 'shop')).lower()
        con.execute('''INSERT INTO metadata_latest VALUES(?,?,?,?,?,?) ON CONFLICT(listing_id) DO UPDATE
          SET id=excluded.id,captured_at=excluded.captured_at,available_at=excluded.available_at,payload=excluded.payload,search_text=excluded.search_text
          WHERE (excluded.captured_at,excluded.available_at,excluded.id)>(metadata_latest.captured_at,metadata_latest.available_at,metadata_latest.id)''',
          (value['listing_id'], ident, value['captured_at'], value['available_at'], encoded(value), search))
    return cursor.rowcount


def counts():
    with database() as con:
        result = {table: con.execute(f'SELECT count(*) FROM {table}' + (' INDEXED BY metadata_count' if table == 'metadata' else '')).fetchone()[0]
                  for table in ('observations', 'artifacts', 'metadata', 'jobs', 'outcomes', 'models', 'predictions')}
        result['listings'] = con.execute('SELECT count(*) FROM metadata_latest').fetchone()[0]
        result['reference_listings'] = con.execute("SELECT count(DISTINCT listing_id) FROM observations WHERE metric='estimated_sales'").fetchone()[0]
        result['worker'] = get_control(con, 'worker', {'status': 'not_started'})
        result['paused'] = get_control(con, 'paused', False)
        result['catalog'] = get_control(con, 'catalog', {})
        result['automatic_estimator'] = get_control(con, 'estimator', {'tracked': 0, 'estimated': 0})
        return result
