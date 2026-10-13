"""Bounded read-only import from a preserved collector into the native writer.

Archive every imported row before projecting it, and checkpoint in the same
transaction. Original scans stay source-labelled archives, never native scans.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

TABLES = ('seeds', 'evidence_collection_runs', 'keyword_observations',
          'keyword_suggestions', 'keyword_trend_points', 'keyword_listing_snapshots', 'scans')


def encoded(row):
    return json.dumps(dict(row), sort_keys=True, separators=(',', ':'), allow_nan=False)


def anchor(row):
    # Stable identity, excluding mutable run completion fields.
    if row is None:
        return None
    value = dict(row)
    return hashlib.sha256(json.dumps({k: value[k] for k in ('id', 'keyword') if k in value}, sort_keys=True).encode()).hexdigest()


def capture_baseline(path):
    """The full prior reconciliation snapshot is already retained separately."""
    if not Path(path).exists():
        return {}
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as source:
        source.row_factory = sqlite3.Row
        result = {}
        names = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in TABLES:
            if table in names:
                row = source.execute(f'SELECT rowid AS bridge_rowid,* FROM {table} ORDER BY rowid DESC LIMIT 1').fetchone()
                result[table] = {'last_rowid': row['bridge_rowid'] if row else 0, 'anchor_sha256': anchor(row)}
        return result


def import_incremental(con, source_path, baseline=None, origin='original-collector', limit=10000):
    source_path = Path(source_path).resolve()
    if not source_path.is_file():
        return {'status': 'source_unavailable', 'imported_rows': 0}
    if source_path == Path(con.execute('PRAGMA database_list').fetchone()[2]).resolve():
        raise ValueError('Cannot bridge a database to itself')
    imported = {}; remaining = max(1, min(int(limit), 20000)); pending = 0
    source = sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True, timeout=15)
    source.row_factory = sqlite3.Row
    try:
        source.execute('BEGIN')  # One consistent source read; never mutate it.
        names = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in TABLES:
            if table not in names:
                continue
            cursor = con.execute('SELECT * FROM feed_import_checkpoints WHERE origin=? AND table_name=?', (origin, table)).fetchone()
            if not cursor:
                initial = (baseline or {}).get(table, {})
                con.execute('INSERT INTO feed_import_checkpoints VALUES(?,?,?,?)', (origin, table, initial.get('last_rowid', 0), initial.get('anchor_sha256')))
                cursor = con.execute('SELECT * FROM feed_import_checkpoints WHERE origin=? AND table_name=?', (origin, table)).fetchone()
            if cursor['last_rowid']:
                old = source.execute(f'SELECT * FROM {table} WHERE rowid=?', (cursor['last_rowid'],)).fetchone()
                if old is None or (cursor['anchor_sha256'] and anchor(old) != cursor['anchor_sha256']):
                    raise ValueError('OriginalCollectorHistoryChangedRequiresReview')
            available = source.execute(f'SELECT count(*) FROM {table} WHERE rowid>?', (cursor['last_rowid'],)).fetchone()[0]
            # Reserve work for each table so suggestions cannot starve trend/scan history.
            weights = {'seeds': .02, 'evidence_collection_runs': .16, 'keyword_observations': .06,
                       'keyword_suggestions': .54, 'keyword_trend_points': .02,
                       'keyword_listing_snapshots': .02, 'scans': .18}
            budget = max(1, min(remaining, max(1, int(limit * weights[table])))) if remaining else 0
            rows = source.execute(f'SELECT rowid AS bridge_rowid,* FROM {table} WHERE rowid>? ORDER BY rowid LIMIT ?', (cursor['last_rowid'], budget)).fetchall()
            added = 0
            for row in rows:
                raw = dict(row); rowid = raw.pop('bridge_rowid'); payload = encoded(raw)
                fingerprint = hashlib.sha256(payload.encode()).hexdigest()
                inserted = con.execute('INSERT OR IGNORE INTO feed_import_records VALUES(?,?,?,?,?,?)',
                    (origin, table, rowid, fingerprint, payload, datetime.now(timezone.utc).isoformat())).rowcount
                if inserted:
                    _project(con, table, raw, origin); added += 1
                else:
                    previous = con.execute('SELECT sha256 FROM feed_import_records WHERE origin=? AND table_name=? AND source_rowid=?', (origin, table, rowid)).fetchone()[0]
                    if previous != fingerprint:
                        raise ValueError('ArchivedCollectorRowChangedRequiresReview')
                con.execute('UPDATE feed_import_checkpoints SET last_rowid=?,anchor_sha256=? WHERE origin=? AND table_name=?', (rowid, anchor(raw), origin, table))
            imported[table] = added; remaining -= len(rows); pending += available - len(rows)
        return {'status': 'catching_up' if pending else 'current', 'imported_rows': sum(imported.values()),
                'pending_rows': pending, 'tables': imported, 'original_modified': False}
    finally:
        source.close()


def _project(con, table, raw, origin):
    if table == 'scans':
        return  # Preserve raw source scans without colliding with native IDs/checkpoints.
    row = dict(raw)
    if table != 'evidence_collection_runs':
        row.pop('id', None)
    else:
        row['id'] = 'bridge:' + origin + ':' + str(row['id'])
        row.update(durable_sync_status='source_archive', durable_synced_at=None, durable_sync_error=None)
    for field in (() if table == 'seeds' else ('keyword', 'parent_keyword')):
        if row.get(field):
            timestamp = row.get('observed_at') or row.get('collected_at') or datetime.now(timezone.utc).isoformat()
            con.execute('INSERT OR IGNORE INTO seeds(keyword,domain,source,added_at) VALUES(?,?,?,?)', (row[field], 'discovered', 'collector_bridge', timestamp))
    if row.get('collection_run_id'):
        identity = 'bridge:' + origin + ':' + str(row['collection_run_id'])
        # A bounded chunk may not have imported the parent yet. Do not create
        # an invalid FK; the archived source row retains the complete lineage.
        row['collection_run_id'] = identity if con.execute('SELECT 1 FROM evidence_collection_runs WHERE id=?', (identity,)).fetchone() else None
    allowed = {r[1] for r in con.execute('PRAGMA table_info(' + table + ')')}
    row = {k: v for k, v in row.items() if k in allowed}
    fields = ','.join('"' + k + '"' for k in row)
    con.execute(f'INSERT OR IGNORE INTO {table}({fields}) VALUES({",".join("?" for _ in row)})', tuple(row.values()))
