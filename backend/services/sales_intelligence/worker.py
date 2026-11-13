"""App-owned durable jobs. No third-party endpoint is guessed from a browser UI."""
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import shutil
import sqlite3
from . import estimator, features, ingestion, quotas, registry, store, training

LEASE_SECONDS = 900


def enqueue(kind, payload=None, identity=None):
    if kind not in ('catalog', 'backfill', 'import', 'train', 'predict', 'evaluate_actual', 'promote', 'fetch', 'estimate'):
        raise ValueError('Unsupported research job')
    payload = payload or {}
    source = payload.get('source_id', 'local')
    ident = store.digest({'kind': kind, 'payload': payload, 'request': identity or store.now().isoformat()})
    with store.database(True) as con:
        con.execute('INSERT OR IGNORE INTO jobs(id,source_id,status,due_at,payload) VALUES(?,?,?,?,?)',
                    (ident, source, 'queued', store.now().isoformat(), store.encoded({'kind': kind, **payload})))
    return {'id': ident, 'status': 'queued', 'collection_owner': 'etgen_backend'}


def import_inbox():
    inbox = store.root() / 'imports/inbox'
    if not inbox.is_dir():
        return {'status': 'no_exports', 'imported': 0}
    imported, failures = 0, []
    for path in sorted(inbox.glob('*.json'))[:4]:
        resolved = path.resolve()
        if not resolved.is_relative_to(inbox.resolve()) or path.is_symlink():
            continue
        if path.stat().st_size > ingestion.MAX_BYTES:
            failures.append({'file': path.name, 'reason': 'oversize'})
            continue
        before = path.stat()
        content = path.read_bytes()
        if path.stat().st_mtime_ns != before.st_mtime_ns:
            continue
        identity = store.digest(content.hex())
        with store.database() as con:
            if store.get_control(con, 'inbox:' + identity):
                continue
        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError('Inbox JSON must contain the source and import envelope')
            if registry.source(data.get('source_id'))['paused']:
                continue
            check = ingestion.preview(data)
            ingestion.commit({**data, 'expected_fingerprint': check['fingerprint']})
            # Preserve the operator's original inbox file; processed receipt is in DB.
            with store.database(True) as con:
                store.set_control(con, 'inbox:' + identity, {'status': 'processed', 'at': store.now().isoformat()})
            imported += 1
        except (ValueError, TypeError, KeyError) as exc:
            failures.append({'file': path.name, 'reason': str(exc)[:200]})
    return {'status': 'needs_attention' if failures else 'processed', 'imported': imported, 'failures': failures}


def plan():
    sources = registry.sources()
    with store.database() as con:
        panel = con.execute('SELECT payload FROM panels ORDER BY rowid DESC LIMIT 1').fetchone()
        listing_ids = json.loads(panel[0])['listing_ids'] if panel else []
    scheduled = []
    for source in sources:
        if source['automation'] != 'supported_api_configured' or source['paused']:
            continue
        retry_at = source.get('health', {}).get('retry_at')
        if retry_at and store.stamp(retry_at) > store.now():
            continue
        grant = registry.grants()[source['id']]
        with store.database() as con:
            try:
                allowance = quotas.state(con, source['id'])
            except (ValueError, KeyError, TypeError):
                continue
            cost = grant.get('cost_per_request', 1)
            if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost <= 0:
                continue
            slots = min(2, int(allowance['remaining'] / cost))
            latest = {r['listing_id']: r['last'] for r in con.execute('SELECT listing_id,max(captured_at) last FROM observations WHERE source_id=? GROUP BY listing_id', (source['id'],))}
        cutoff = store.now() - timedelta(hours=max(24, float(grant.get('refresh_hours', 24))))
        due = sorted((identity for identity in listing_ids if identity not in latest or store.stamp(latest[identity]) < cutoff),
                     key=lambda identity: (latest.get(identity, ''), store.digest(identity)))
        scheduled.extend({'source_id': source['id'], 'listing_id': identity} for identity in due[:slots])
    return {'collection_owner': 'etgen_backend', 'external_requests_planned': len(scheduled), 'requests': scheduled,
            'listing_ids': listing_ids, 'supported_acquisition': ['protected_export_inbox'],
            'sources': [{'id': s['id'], 'status': s['disposition'], 'reason': s['reason'],
                         'storage_eligible': s['capabilities']['storage'], 'paused': s['paused']} for s in sources],
            'blocker': None if scheduled else 'No verified free automated provider API is configured or the reference panel is empty; export ingestion does not automate exporting'}


def dispatch_collection(source_id=None):
    with store.database() as con:
        if store.get_control(con, 'paused', False):
            return {'status': 'paused', 'external_requests': 0, 'queued': 0}
    preview = plan()
    requests = [r for r in preview['requests'] if source_id is None or r['source_id'] == source_id]
    if source_id:
        requests = requests[:1]
    for request in requests:
        identity = store.digest({'source': request['source_id'], 'listing': request['listing_id'], 'day': store.now().date().isoformat()})
        enqueue('fetch', {**request, 'reservation_id': identity}, identity=identity)
    return {'status': 'queued' if requests else 'no_due_eligible_sources', 'queued': len(requests), 'external_requests': 0,
        'reason': None if requests else preview['blocker'] or 'No due requests for this source'}


def execute(payload):
    kind = payload['kind']
    if kind == 'estimate':
        return estimator.refresh()
    if kind == 'fetch':
        from .adapters import fetch
        return fetch(payload['source_id'], payload['listing_id'], payload['reservation_id'])
    if kind == 'catalog':
        return {**features.sync_catalog(), 'saved_api': features.sync_raw_catalog()}
    if kind == 'backfill':
        return {**features.sync_catalog(backfill=True), 'saved_api': features.sync_raw_catalog(backfill=True)}
    if kind == 'import':
        return import_inbox()
    if kind == 'train':
        result = training.fit(payload.get('days', 30), payload.get('unit', 'purchases'), payload.get('objective', 'consensus'))
        if result.get('qualified'):
            with store.database() as con:
                active_id = store.get_control(con, training.active_key(result))
                active_row = con.execute('SELECT payload FROM models WHERE id=?', (active_id,)).fetchone() if active_id else None
            current = json.loads(active_row[0]) if active_row else None
            # Compare only common frozen test cases, never two unrelated scores.
            if not current or (current['test_ids'] == result['test_ids'] and result['evaluation']['mae'] < current['evaluation']['mae']):
                result['activation'] = training.activate(result['id'])
                enqueue('predict', {'days': result['days'], 'unit': result['unit'], 'lane': result['lane']}, identity=result['id'])
        return result
    if kind == 'predict':
        with store.database() as con:
            ids = [r[0] for r in con.execute('SELECT DISTINCT listing_id FROM metadata WHERE listing_id>? ORDER BY listing_id LIMIT 100', (payload.get('after', ''),))]
        statuses = {}
        for identity in ids:
            result = training.prediction(identity, payload.get('days', 30), payload.get('unit', 'purchases'), lane=payload.get('lane', 'consensus_student'))
            statuses[result['status']] = statuses.get(result['status'], 0) + 1
        if len(ids) == 100:
            enqueue('predict', {**payload, 'after': ids[-1]}, identity=store.now().date().isoformat())
        return {'processed': len(ids), 'statuses': statuses, 'after': ids[-1] if ids else None}
    if kind == 'evaluate_actual':
        return training.evaluate_actual(payload['model_id'])
    if kind == 'promote':
        from .service import flush_outbox
        return flush_outbox()
    raise ValueError('Unknown job')


def cycle():
    from services.app_keyword_feed import supervisor_lock
    with supervisor_lock(store.root() / 'worker.lock') as acquired:
        if not acquired:
            return {'status': 'already_running'}
        at = store.now()
        with store.database(True) as con:
            if store.get_control(con, 'paused', False):
                return {'status': 'paused'}
            if shutil.disk_usage(store.root()).free < 512 * 1024 * 1024:
                store.set_control(con, 'worker', {'status': 'disk_low', 'at': at.isoformat()})
                return {'status': 'disk_low'}
            con.execute("UPDATE jobs SET status='interrupted',lease_until=NULL WHERE status='running' AND lease_until<?", (at.isoformat(),))
            con.execute("UPDATE jobs SET status='failed' WHERE status='interrupted' AND attempts>=3")
            reservations_before = con.execute('SELECT count(*) FROM quota_events').fetchone()[0]
        for kind in ('catalog', 'backfill', 'import', 'promote', 'estimate'):
            enqueue(kind, identity=at.strftime('%Y-%m-%dT%H:%M'))
        with store.database() as con:
            has_panel = con.execute('SELECT 1 FROM panels LIMIT 1').fetchone()
            has_metadata = con.execute('SELECT 1 FROM metadata LIMIT 1').fetchone()
        if not has_panel and has_metadata:
            features.panel()
        collection = plan()
        for request in collection['requests']:
            identity = store.digest({'source': request['source_id'], 'listing': request['listing_id'], 'day': at.date().isoformat()})
            enqueue('fetch', {**request, 'reservation_id': identity}, identity=identity)
        # Weekly eligibility check is cheap on empty data; actual fitting is guarded.
        with store.database() as con:
            last = store.get_control(con, 'last_train_check', '')
        if not last or store.stamp(last) < at - timedelta(days=7):
            for objective in ('consensus', 'actual'):
                enqueue('train', {'objective': objective}, identity=at.strftime('%Y-%W'))
            with store.database(True) as con:
                store.set_control(con, 'last_train_check', at.isoformat())
        with store.database() as con:
            active = [json.loads(r['payload']) for r in con.execute("SELECT payload FROM models WHERE id IN (SELECT json_extract(value,'$') FROM control WHERE key LIKE 'active:%')")]
        for model in active:
            enqueue('predict', {'days': model['days'], 'unit': model['unit'], 'lane': model['lane']}, identity=at.date().isoformat())
        completed = []
        for _ in range(8):
            with store.database(True) as con:
                if store.get_control(con, 'paused', False):
                    break
                row = con.execute("SELECT * FROM jobs WHERE status IN ('queued','interrupted') AND due_at<=? AND attempts<3 ORDER BY due_at,id LIMIT 1", (at.isoformat(),)).fetchone()
                if not row:
                    break
                con.execute("UPDATE jobs SET status='running',lease_until=?,attempts=attempts+1 WHERE id=?", ((at + timedelta(seconds=LEASE_SECONDS)).isoformat(), row['id']))
            try:
                result = execute(json.loads(row['payload']))
                status = 'completed'
            except Exception as exc:
                # Never retain provider bodies, credentials or filesystem paths in error output.
                result, status = {'error': type(exc).__name__}, 'failed'
                if isinstance(exc, sqlite3.OperationalError) and json.loads(row['payload'])['kind'] != 'fetch' and row['attempts'] < 2:
                    status = 'interrupted'
            with store.database(True) as con:
                due_at = (at + timedelta(seconds=60 * 2 ** row['attempts'])).isoformat() if status == 'interrupted' else row['due_at']
                con.execute('UPDATE jobs SET status=?,lease_until=NULL,result=?,due_at=? WHERE id=?', (status, store.encoded(result), due_at, row['id']))
            completed.append({'id': row['id'], 'status': status, 'kind': json.loads(row['payload'])['kind']})
        with store.database() as con:
            external = con.execute('SELECT count(*) FROM quota_events').fetchone()[0] - reservations_before
        result = {'status': 'needs_attention' if any(j['status'] == 'failed' for j in completed) else 'idle',
                  'at': at.isoformat(), 'jobs': completed, 'external_request_jobs': sum(j['kind'] == 'fetch' for j in completed),
                  'external_requests': external, 'request_accounting': 'durable_reservations_including_uncertain_dispatch', 'owner': 'etgen_backend'}
        with store.database(True) as con:
            store.set_control(con, 'worker', result)
        return result


class Worker:
    def __init__(self):
        self.task = None
        self.state = {'last_outcome': 'starting'}

    async def run(self):
        await asyncio.sleep(5)
        while True:
            try:
                result = await asyncio.to_thread(cycle)
                self.state = {'last_outcome': result['status'], 'checked_at': store.now().isoformat()}
            except Exception as exc:
                # A temporary archive/disk failure must not kill the app-owned loop.
                self.state = {'last_outcome': 'needs_attention', 'error_class': type(exc).__name__, 'checked_at': store.now().isoformat()}
            await asyncio.sleep(60)

    def start(self):
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


def configured_worker():
    enabled = os.environ.get('APP_SALES_INTELLIGENCE_ENABLED', os.environ.get('APP_KEYWORD_FEED_ENABLED', '0'))
    return Worker() if enabled == '1' else None
