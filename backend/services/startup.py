"""Small, read-only operator views. Never serialize evidence packets or customer inputs."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from services import product_validation as validation


def connection(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=2)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    deadline = time.monotonic() + 3
    con.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
    con.execute('BEGIN')
    return con


def projects(limit=50):
    with closing(connection(validation.db_path())) as con:
        total = con.execute("SELECT count(*) FROM records WHERE kind='project'").fetchone()[0]
        rows = con.execute("""SELECT project_id id, json_extract(payload,'$.name') name,
            json_extract(payload,'$.product_type') product_type, updated_at
            FROM records WHERE kind='project' ORDER BY updated_at DESC,id LIMIT ?""", (limit,))
        items = [dict(row) for row in rows]
        if len({row['id'] for row in items}) != len(items) or any(not isinstance(row['name'], str) or not row['id'] for row in items):
            raise ValueError('Incomplete project header')
        return {'status': 'ready', 'projects': items, 'total': total,
                'has_more': total > len(items)}


def production(limit=24):
    path = Path(os.getenv('PRODUCTION_ROOT', validation.db_path().parent/'production'))/'production.sqlite'
    with closing(connection(path)) as con:
        total = con.execute('SELECT count(DISTINCT product_id) FROM jobs').fetchone()[0]
        setting = con.execute("SELECT value FROM settings WHERE name='paused'").fetchone()
        rows = con.execute("""WITH current AS (
            SELECT id,product_id,revision,status,updated_at,created_at,
                row_number() OVER(PARTITION BY product_id ORDER BY created_at DESC,rowid DESC) position
            FROM jobs)
            SELECT j.id,j.product_id,j.revision,j.status,j.updated_at,
                json_extract(s.payload,'$.name') name,json_extract(s.payload,'$.family') family,
                json_extract(s.payload,'$.schema_version') schema_version,
                json_extract(detail.result,'$.manifest.render.previews') previews
            FROM current j JOIN specs s ON s.product_id=j.product_id AND s.revision=j.revision
            JOIN jobs detail ON detail.id=j.id
            WHERE j.position=1 ORDER BY j.created_at DESC,j.id LIMIT ?""", (limit,))
        jobs = []
        for row in rows:
            if not row['name'] or not row['family']:
                raise ValueError('Incomplete production header')
            # Preserve the existing customer-data mirror boundary for v2 products.
            name = row['family'].replace('_', ' ').title() if row['schema_version'] == 2 else row['name']
            jobs.append({key: row[key] for key in ('id', 'product_id', 'revision', 'status', 'updated_at')} |
                        {'spec': {'name': name, 'family': row['family']},
                         'has_preview': bool(row['previews'])})
        return {'status': 'ready', 'jobs': jobs, 'total': total, 'has_more': total > len(jobs),
                'paused': bool(setting and setting[0] == '1'), 'human_approval_required': True}


def summary():
    result = {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
              'source': 'authoritative_operator_databases'}
    for name, load, key in [('projects', projects, 'projects'), ('production', production, 'jobs')]:
        try:
            result[name] = load()
        except (sqlite3.Error, OSError, ValueError):
            result[name] = {'status': 'unavailable', key: None, 'total': None,
                            'error': 'Saved ' + name + ' could not be read. Retry the connection.'}
    result['input_fingerprint'] = hashlib.sha256(json.dumps(
        {k: v for k, v in result.items() if k != 'generated_at'}, sort_keys=True).encode()).hexdigest()
    return result
