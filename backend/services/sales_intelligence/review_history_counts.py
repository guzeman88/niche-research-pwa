"""Opt-in, durable one-off API count acquisition in the existing backend turn.

Configuration and results stay below the private archive. This module never
fits a model, imports operator code, or creates a scheduler or public endpoint.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import uuid

from . import review_history_count_collector as collector, store

SPACING_SECONDS = 900
MAX_CALLS = 40
class ResearchPaused(RuntimeError):
    pass


OUTPUT_FILES = ('state.json', 'reference-inputs.jsonl', 'counts-by-reference.jsonl',
                'terminal-state.json', 'counts-completion.json', 'last-pass.json',
                'backend-gate.json', 'backend-last-pass.json')


def now():
    return datetime.now(timezone.utc)


def root():
    base = store.root().resolve()
    path = base / 'review-history-counts'
    if path.is_symlink() or not path.resolve().is_relative_to(base):
        raise ValueError('Research directory escapes private archive')
    return path


def _path(base, name, *, plan=False):
    pattern = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.json' if plan else r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}'
    if not isinstance(name, str) or not re.fullmatch(pattern, name):
        raise ValueError('Research paths must be relative basenames')
    path = base / name
    if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
        raise ValueError('Research path escapes private archive')
    return path


def _json(path, max_bytes=2_000_000):
    if path.is_symlink() or path.stat().st_size > max_bytes:
        raise ValueError('Research file is unsafe or oversized')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Research JSON must be an object')
    return value


def _configuration():
    base = root()
    path = base / 'config.json'
    if not path.exists():
        return None
    config = _json(path, 16_384)
    if type(config.get('enabled')) is not bool:
        raise ValueError('Research enabled must be boolean')
    if not config['enabled']:
        return None
    if set(config) - {'enabled', 'plan_file', 'plan_sha256', 'output_directory', 'not_before_utc'}:
        raise ValueError('Unknown research configuration field')
    if not re.fullmatch('[0-9a-f]{64}', str(config.get('plan_sha256', ''))):
        raise ValueError('Exact plan hash required')
    plan_path = _path(base, config['plan_file'], plan=True)
    output = _path(base, config['output_directory'])
    if not plan_path.is_file() or plan_path.stat().st_size > 2_000_000:
        raise ValueError('Research plan is unavailable or oversized')
    if collector.sha(plan_path) != config['plan_sha256']:
        raise ValueError('Research plan hash changed')
    plan = collector.plan_value(_json(plan_path))
    if any(not 946684800 <= q['params']['max_created'] < now().timestamp() for q in plan['requests']):
        raise ValueError('Research review cutoffs must be historical API timestamps')
    for name in OUTPUT_FILES:
        for candidate in (output / name, output / (name + '.tmp'), (output / name).with_suffix('.json.tmp')):
            if candidate.is_symlink() or not candidate.resolve().is_relative_to(base.resolve()):
                raise ValueError('Research output escapes private archive')
    not_before = store.stamp(config['not_before_utc']) if config.get('not_before_utc') else None
    return base, config, plan_path, output, plan, not_before


def _state(output, config, plan):
    path = output / 'state.json'
    if not path.exists():
        return None
    state = _json(path)
    if (state.get('version') != collector.VERSION or state.get('plan_sha256') != collector.digest(plan)
            or state.get('plan_file_sha256') != config['plan_sha256']
            or [r['request_key'] for r in state['requests']] != [r['request_key'] for r in plan['requests']]):
        raise ValueError('Saved research state does not match frozen plan')
    return state


def _due(output, config, plan, not_before):
    latest = not_before
    terminal_status = None
    state = _state(output, config, plan)
    if state:
        if state.get('halted'):
            terminal_status = 'halted'
        if not terminal_status and all(r['status'] in ('complete', 'reused', 'unknown') for r in state['requests']):
            if (output / 'counts-completion.json').is_file():
                terminal_status = 'complete'
        for receipt in state['passes']:
            if receipt['requests']:
                finished = store.stamp(receipt['finished_at_utc']) + timedelta(seconds=SPACING_SECONDS)
                latest = max(latest, finished) if latest else finished
    gate_path = output / 'backend-gate.json'
    if gate_path.exists():
        gate = _json(gate_path, 16_384)
        if gate.get('plan_sha256') != config['plan_sha256']:
            raise ValueError('Research gate belongs to another plan')
        finished = store.stamp(gate['finished_at_utc']) + timedelta(seconds=SPACING_SECONDS)
        latest = max(latest, finished) if latest else finished
    if latest and now() < latest:
        return 'not_due', latest.isoformat()
    return terminal_status or 'due', None


def _paused(native_root):
    native = native_root / 'state.sqlite'
    sales = store.root() / 'intelligence.sqlite'
    if not native.is_file() or not sales.is_file():
        raise ValueError('Research pause state is unavailable')
    with closing(sqlite3.connect(native.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as con:
        if con.execute("SELECT 1 FROM control WHERE name='paused'").fetchone():
            return True
    with closing(sqlite3.connect(sales.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as con:
        row = con.execute("SELECT value FROM control WHERE key='paused'").fetchone()
        if row:
            value = json.loads(row[0])
            if type(value) is not bool:
                raise ValueError('Research pause state is invalid')
            return value
    return False


def _result(status, requests=0, **extra):
    return {'status': status, 'requests': requests, 'owner': 'etgen_backend',
            'source_eligibility': False, 'activation': False, **extra}


def cycle():
    """Use at most one existing product-research turn before the native cycle."""
    from services import feed_request_budget as budget, selling_discovery as discovery, selling_discovery_sources as sources
    from services.app_keyword_feed import supervisor_lock

    result = _result('disabled')
    try:
        configured = _configuration()
        if configured is None:
            return result
        _base, config, plan_path, output, plan, not_before = configured
        status, retry_at = _due(output, config, plan, not_before)
        if status != 'due':
            return _result(status, retry_at=retry_at)
        native_root = discovery.native_root()
        if _paused(native_root):
            return _result('paused')
        access = discovery.approval()
        if 'listing_reviews' not in access['scopes']:
            return _result('authorization_unverified')
        database = discovery.native_database()
        if database is None:
            return _result('catalog_unavailable')
        with supervisor_lock(native_root / 'worker.lock') as acquired:
            if not acquired:
                return _result('native_collector_running')
            # A process may have completed while this invocation awaited its turn.
            status, retry_at = _due(output, config, plan, not_before)
            if status != 'due':
                return _result(status, retry_at=retry_at)
            if _paused(native_root):
                return _result('paused')
            output.mkdir(parents=True, exist_ok=True)
            started = now().isoformat()
            with closing(sqlite3.connect(database, timeout=20)) as con:
                budget.schema(con)
                client = sources.Client(con, 'selling-discovery-review-history-' + uuid.uuid4().hex, access['scopes'])
                try:
                    client.batch_limit = min(client.batch_limit, MAX_CALLS)
                    get = client.get
                    def permitted_get(path, scope, params=None):
                        if _paused(native_root):
                            raise ResearchPaused()
                        return get(path, scope, params)
                    client.get = permitted_get
                    collected = collector.collect(client, plan_path, output)
                    result = _result(collected['status'], **{key: collected[key] for key in
                        ('accepted_reference_rows', 'accepted_requests', 'pending_requests', 'unknown_requests', 'halted')})
                except budget.CollectionDeferred:
                    result = _result('budget_deferred')
                except ResearchPaused:
                    result = _result('paused')
                except sources.SourceUnavailable:
                    result = _result('source_unavailable')
                except Exception as exc:
                    result = _result('research_needs_attention', error_type=type(exc).__name__)
                finally:
                    result['requests'] = client.requests
                    finished = now().isoformat()
                    # The collector's own finally already preserves its counted
                    # pass. Keep scheduling metadata separate from its export.
                    try:
                        if client.requests:
                            collector.write(output / 'backend-gate.json', {'plan_sha256': config['plan_sha256'],
                                'finished_at_utc': finished, 'requests': client.requests})
                            result['retry_at'] = (store.stamp(finished) + timedelta(seconds=SPACING_SECONDS)).isoformat()
                    finally:
                        try:
                            client.close()
                        except Exception:
                            result['status'] = 'research_needs_attention'
                    receipt = {'started_at_utc': started, 'finished_at_utc': finished,
                               'plan_sha256': config['plan_sha256'], **result,
                               'finalized_under_native_lease': True}
                    collector.write(output / 'backend-last-pass.json', receipt)
        return result
    except Exception as exc:
        # Never leak config paths, provider bodies or credentials through health.
        return _result('research_needs_attention', result['requests'], error_type=type(exc).__name__)
