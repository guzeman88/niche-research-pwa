"""Durable native Etsy request accounting, including pages and interrupted calls."""
from datetime import datetime, timedelta, timezone
import json
import gzip
import os
import time


class CollectionDeferred(RuntimeError):
    """A budget/backoff boundary, not an empty provider result."""


def schema(con):
    con.executescript('''CREATE TABLE IF NOT EXISTS feed_etsy_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL,
        attempted_at TEXT NOT NULL, status TEXT NOT NULL, quota_json TEXT,
        request_json TEXT, response_gzip BLOB);
        CREATE INDEX IF NOT EXISTS feed_etsy_requests_time ON feed_etsy_requests(attempted_at);''')


def latest_quota(con):
    row = con.execute("SELECT quota_json FROM feed_etsy_requests WHERE quota_json IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    return json.loads(row[0]) if row else {}


def claim(con, quota, batch_id, batch_limit, daily_limit=4000, at=None):
    at = at or datetime.now(timezone.utc)
    con.execute('BEGIN IMMEDIATE')
    stored = latest_quota(con)
    # Live headers supersede old remaining counts; persisted retry-after survives restart.
    if stored.get('retry_after_until', 0) and stored['retry_after_until'] > time.time():
        raise CollectionDeferred('Provider backoff')
    daily = quota.get('limit_per_day') or stored.get('limit_per_day')
    remaining = quota.get('remaining_today') if quota.get('remaining_today') is not None else stored.get('remaining_today')
    if daily and remaining is not None and remaining <= daily * .2:
        captured = stored.get('captured_at')
        # At most one probe/hour when saved quota is exhausted; never a request storm.
        if not captured or at - datetime.fromisoformat(captured) < timedelta(hours=1):
            raise CollectionDeferred('Rolling quota reserve')
    cutoff = (at - timedelta(hours=24)).isoformat()
    used = con.execute('SELECT count(*) FROM feed_etsy_requests WHERE attempted_at>=?', (cutoff,)).fetchone()[0]
    ceiling = min(daily_limit, int(daily * .8)) if daily else daily_limit
    batch_used = con.execute('SELECT count(*) FROM feed_etsy_requests WHERE batch_id=?', (batch_id,)).fetchone()[0]
    if used >= ceiling or batch_used >= batch_limit:
        raise CollectionDeferred('Native request budget')
    recent = con.execute('SELECT status FROM feed_etsy_requests WHERE batch_id=? ORDER BY id DESC LIMIT 5', (batch_id,)).fetchall()
    if len(recent) == 5 and all(r[0] not in {'200', '201'} for r in recent):
        raise CollectionDeferred('Repeated request failures')
    if not daily and batch_used:
        raise CollectionDeferred('No observed provider quota after probe')
    identity = con.execute("INSERT INTO feed_etsy_requests(batch_id,attempted_at,status) VALUES(?,?,'in_flight')", (batch_id, at.isoformat())).lastrowid
    con.commit()  # Count an interrupted/failed request before contacting the provider.
    return identity


def start_request(quota):
    from pipeline import keyword_database as db
    with db._conn() as con:
        return claim(con, quota, os.environ['FEED_ETSY_BATCH_ID'], int(os.environ['FEED_ETSY_REQUEST_BUDGET']))


def finish_request(identity, status, quota, path=None, params=None, payload=None):
    from pipeline import keyword_database as db
    value = {**quota, 'captured_at': datetime.now(timezone.utc).isoformat()}
    with db._conn() as con:
        con.execute('UPDATE feed_etsy_requests SET status=?,quota_json=?,request_json=?,response_gzip=? WHERE id=?',
                    (status, json.dumps(value), json.dumps({'path': path, 'params': params}),
                     gzip.compress(json.dumps(payload).encode()) if payload is not None else None, identity))
