"""Isolated durable research acquisition. No provider, installation or live DB."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from services import app_keyword_feed as feed, selling_discovery as discovery, selling_discovery_sources as sources
from services import feed_request_budget as budget
from services.sales_intelligence import review_history_counts as research

collector = research.collector


def plan_fixture(size=45, reuses=3, zero=False):
    refs, requests = [], []
    cutoff = datetime(2026, 10, 31, tzinfo=timezone.utc)
    for index in range(size):
        lid, sid = str(1000 + index), str(700 + index)
        q = {'listing_id': lid, 'shop_id': sid, 'path': '/listings/' + lid + '/reviews',
             'scope': 'listing_reviews', 'params': {'limit': 1, 'offset': 0,
             'min_created': 946684800, 'max_created': int(cutoff.timestamp()) - 1},
             'reference_ids': ['ref-' + lid], 'known_dated30d_count_max': 0 if zero else 1,
             'reuse': None}
        q['request_key'] = collector.request_key(q)
        if index < reuses:
            q['reuse'] = {'count': 8, 'shop_id': sid, 'sample_identity_matches': True,
                          'sample_timestamp_in_bounds': True, 'sample_rating_valid': True,
                          'captured_at_utc': cutoff.isoformat()}
        requests.append(q)
        refs.append({'reference_id': 'ref-' + lid, 'cohort': 'fixture', 'listing_id': lid,
                     'shop_id': sid, 'cutoff_utc': cutoff.isoformat(),
                     'window_start_utc': (cutoff - timedelta(days=30)).isoformat(),
                     'known_dated30d_count': 0 if zero else 1, 'provider_exact_cutoff_known': False,
                     'cutoff_basis': 'isolated_fixture', 'request_key': q['request_key']})
    return {'version': 'listing-review-count-population-plan-1', 'reference_count': size,
            'grouped_request_count': size, 'cohort_reference_counts': {'fixture': size},
            'reused_request_count': reuses, 'new_request_count': size - reuses,
            'max_client_calls_per_pass': 40, 'normal_requestful_spacing_seconds': 900,
            'source_eligibility': False, 'activation': False, 'model_fitting_or_selection': False,
            'references': refs, 'requests': requests}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    archive, native = tmp_path / 'archive', tmp_path / 'native'
    archive.mkdir(); (native / 'data').mkdir(parents=True)
    monkeypatch.setenv('SALES_INTELLIGENCE_ROOT', str(archive))
    monkeypatch.setenv('APP_KEYWORD_FEED_ROOT', str(native))
    with sqlite3.connect(archive / 'intelligence.sqlite') as con:
        con.execute('CREATE TABLE control(key TEXT PRIMARY KEY,value TEXT)')
    with sqlite3.connect(native / 'state.sqlite') as con:
        con.execute('CREATE TABLE control(name TEXT PRIMARY KEY,value TEXT)')
    database = native / 'data/native.sqlite'
    sqlite3.connect(database).close()
    (native / 'installation.json').write_text(json.dumps({'database': str(database)}))
    base = archive / 'review-history-counts'; base.mkdir()
    clock = [datetime(2026, 11, 3, 20, tzinfo=timezone.utc)]
    monkeypatch.setattr(research, 'now', lambda: clock[0])
    monkeypatch.setattr(collector, 'now', lambda: clock[0].isoformat())
    owned, busy, instances, calls = [False], [False], [], []
    before_acquire, action = [None], [None]

    @contextmanager
    def lease(_path):
        if before_acquire[0]:
            before_acquire[0]()
        owned[0] = not busy[0]
        try:
            yield owned[0]
        finally:
            owned[0] = False
    monkeypatch.setattr(feed, 'supervisor_lock', lease)
    monkeypatch.setattr(discovery, 'approval', lambda: {'scopes': ['listing_reviews']})

    class Client:
        def __init__(self, con, identity, scopes):
            assert owned[0]
            assert identity.startswith('selling-discovery-')
            self.requests, self.batch_limit, self.scopes, self.closed = 0, 40, scopes, False
            instances.append(self)
        def get(self, path, scope, params):
            assert owned[0] and self.requests < self.batch_limit
            if action[0]:
                result = action[0](self, path, scope, params)
                if result is not None:
                    return result
            self.requests += 1
            calls.append((path, scope, params))
            lid = path.split('/')[2]; sid = str(int(lid) - 300)
            return {'count': 8, 'results': [{'listing_id': lid, 'shop_id': sid,
                'created_timestamp': params['max_created'] - 10, 'rating': 5,
                'review': 'This private fixture text must never persist', 'buyer_user_id': 999}]}
        def close(self):
            assert owned[0]
            self.closed = True
    monkeypatch.setattr(sources, 'Client', Client)

    def configure(plan=None, **updates):
        data = json.dumps(plan or plan_fixture(), indent=2).encode()
        (base / 'plan.json').write_bytes(data)
        config = {'enabled': True, 'plan_file': 'plan.json',
                  'plan_sha256': hashlib.sha256(data).hexdigest(), 'output_directory': 'run-v1'}
        config.update(updates); (base / 'config.json').write_text(json.dumps(config))
        return config
    return SimpleNamespace(base=base, output=base / 'run-v1', native=native, archive=archive,
        configure=configure, clock=clock, owned=owned, busy=busy, instances=instances,
        calls=calls, action=action, before_acquire=before_acquire)


def test_bounded_pass_restart_gate_reuse_and_terminal_export(rig, monkeypatch):
    rig.configure(plan_fixture(size=250))
    normal_write = collector.write
    writes = []
    def owned_write(path, value):
        assert rig.owned[0]
        writes.append(Path(path).name)
        return normal_write(path, value)
    monkeypatch.setattr(collector, 'write', owned_write)
    first = research.cycle()
    assert first['requests'] == 40 and first['accepted_requests'] == 43 and first['pending_requests'] == 207
    assert len(rig.calls) == 40 and rig.instances[0].closed
    before = {p.name: p.read_bytes() for p in rig.output.iterdir()}
    assert research.cycle()['status'] == 'not_due'
    assert len(rig.instances) == 1 and before == {p.name: p.read_bytes() for p in rig.output.iterdir()}
    rig.clock[0] += timedelta(seconds=899)
    assert research.cycle()['status'] == 'not_due'
    rig.clock[0] += timedelta(seconds=1)
    for expected in (40, 40, 40, 40, 40, 7):
        assert research.cycle()['requests'] == expected
        rig.clock[0] += timedelta(seconds=900)
    assert len({path for path, *_ in rig.calls}) == 247 and len(rig.instances) == 7
    assert research.cycle()['status'] == 'complete'
    counts = rig.output / 'counts-by-reference.jsonl'
    receipt = json.loads((rig.output / 'counts-completion.json').read_text())
    rows = [json.loads(line) for line in counts.read_text().splitlines()]
    assert len(rows) == 250 and receipt['counts_sha256'] == hashlib.sha256(counts.read_bytes()).hexdigest()
    assert all(set(r) == {'reference_id', 'listing_id', 'shop_id', 'cutoff_utc', 'request_key', 'status', 'count', 'captured_at_utc'} for r in rows)
    assert all(r['count'] == 8 for r in rows)
    assert 'backend-gate.json' in writes and 'backend-last-pass.json' in writes
    assert not any('private fixture text' in p.read_text() or 'buyer_user_id' in p.read_text() for p in rig.output.iterdir())


@pytest.mark.parametrize('control', ['native', 'sales'])
def test_pause_and_busy_do_not_create_client_or_rewrite_output(rig, control):
    rig.configure()
    if control == 'native':
        with sqlite3.connect(rig.native / 'state.sqlite') as con:
            con.execute("INSERT INTO control VALUES('paused','true')")
    else:
        with sqlite3.connect(rig.archive / 'intelligence.sqlite') as con:
            con.execute("INSERT INTO control VALUES('paused','true')")
    assert research.cycle()['status'] == 'paused'
    assert not rig.instances and not rig.output.exists()


def test_busy_zero_call_preserves_state_and_rechecks_gate_inside_lease(rig):
    config = rig.configure()
    rig.busy[0] = True
    assert research.cycle()['status'] == 'native_collector_running'
    assert not rig.instances and not rig.output.exists()
    rig.busy[0] = False
    def intervening_pass():
        rig.output.mkdir(exist_ok=True)
        collector.write(rig.output / 'backend-gate.json', {'plan_sha256': config['plan_sha256'],
            'finished_at_utc': rig.clock[0].isoformat(), 'requests': 1})
    rig.before_acquire[0] = intervening_pass
    assert research.cycle()['status'] == 'not_due'
    assert not rig.instances and not (rig.output / 'state.json').exists()


@pytest.mark.parametrize('control', ['native', 'sales'])
def test_midpass_user_pause_stops_before_next_request(rig, control):
    rig.configure(plan_fixture(size=3, reuses=0))
    def action(client, *_args):
        if not client.requests:
            path = rig.native / 'state.sqlite' if control == 'native' else rig.archive / 'intelligence.sqlite'
            with sqlite3.connect(path) as con:
                con.execute("INSERT INTO control VALUES('paused','true')")
    rig.action[0] = action
    result = research.cycle()
    assert result['status'] == 'paused' and result['requests'] == 1
    state = json.loads((rig.output / 'state.json').read_text())
    assert [r['status'] for r in state['requests']] == ['complete', 'pending', 'pending']
    assert state['halted'] is False and rig.instances[0].closed


@pytest.mark.parametrize('failure', ['denial', 'contradiction', 'budget'])
def test_source_boundaries_preserve_unknown_and_close_existing_client(rig, failure):
    rig.configure(plan_fixture(size=3, reuses=0))
    def action(client, *_args):
        if failure == 'budget':
            raise budget.CollectionDeferred('Fixture quota limit')
        client.requests += 1
        if failure == 'denial':
            raise sources.SourceUnavailable('access_denied', 403)
        return {'count': 0, 'results': []}
    rig.action[0] = action
    result = research.cycle()
    assert result['requests'] == (0 if failure == 'budget' else 1)
    assert rig.instances[0].closed
    state = json.loads((rig.output / 'state.json').read_text())
    if failure == 'budget':
        assert result['status'] == 'budget_deferred' and state['requests'][0]['status'] == 'pending'
        assert not (rig.output / 'backend-gate.json').exists()
    else:
        assert state['halted'] and state['requests'][0]['status'] == 'unknown' and state['requests'][0]['count'] is None
        rig.clock[0] += timedelta(seconds=901)
        assert research.cycle()['status'] == 'halted' and len(rig.instances) == 1


def test_uncertain_dispatch_never_gets_retried(rig):
    rig.configure(plan_fixture(size=2, reuses=0))
    assert research.cycle()['requests'] == 2
    for name in ('counts-completion.json', 'counts-by-reference.jsonl', 'terminal-state.json'):
        # These are isolated fixture outputs; production recovery never deletes them.
        (rig.output / name).unlink()
    state = json.loads((rig.output / 'state.json').read_text())
    state['requests'][1].update(status='in_flight', count=None)
    collector.write(rig.output / 'state.json', state)
    rig.clock[0] += timedelta(seconds=901)
    calls = len(rig.calls)
    assert research.cycle()['requests'] == 0 and len(rig.calls) == calls
    state = json.loads((rig.output / 'state.json').read_text())
    assert state['halted'] and state['requests'][1]['status'] == 'unknown'
    assert research.cycle()['status'] == 'halted'


def test_gate_write_failure_still_closes_client_and_uses_collector_gate(rig, monkeypatch):
    rig.configure()
    normal_write = collector.write
    def failed_gate(path, value):
        if Path(path).name == 'backend-gate.json':
            raise OSError('Isolated fixture disk failure')
        return normal_write(path, value)
    monkeypatch.setattr(collector, 'write', failed_gate)
    result = research.cycle()
    assert result['requests'] == 40 and result['status'] == 'research_needs_attention'
    assert rig.instances[0].closed
    assert research.cycle()['status'] == 'not_due'
    assert len(rig.instances) == 1


def test_zero_review_count_is_a_valid_review_observation(rig):
    rig.configure(plan_fixture(size=1, reuses=0, zero=True))
    def action(client, *_args):
        client.requests += 1
        return {'count': 0, 'results': []}
    rig.action[0] = action
    assert research.cycle()['requests'] == 1
    rows = [json.loads(line) for line in (rig.output / 'counts-by-reference.jsonl').read_text().splitlines()]
    assert rows[0]['status'] == 'complete' and rows[0]['count'] == 0


@pytest.mark.parametrize('updates', [{'plan_file': '../private.json'}, {'output_directory': '../private'},
                                     {'plan_sha256': '0' * 64}])
def test_bad_owner_config_fails_closed_without_client_or_path_disclosure(rig, updates):
    rig.configure(**updates)
    result = research.cycle()
    assert result['requests'] == 0 and result['status'] == 'research_needs_attention'
    assert not rig.instances and str(rig.base) not in json.dumps(result)


def test_disabled_missing_and_handoff_not_before_are_zero_call(rig):
    assert research.cycle()['status'] == 'disabled'
    rig.configure(enabled=False)
    assert research.cycle()['status'] == 'disabled'
    rig.configure(not_before_utc=(rig.clock[0] + timedelta(seconds=900)).isoformat())
    assert research.cycle()['status'] == 'not_due' and not rig.instances


def test_changed_plan_needs_new_output_and_preserves_original_state(rig):
    rig.configure()
    assert research.cycle()['requests'] == 40
    before = {p.name: p.read_bytes() for p in rig.output.iterdir()}
    changed = plan_fixture(); changed['reference_inclusion'] = 'New operator metadata'
    rig.configure(changed)
    rig.clock[0] += timedelta(seconds=901)
    assert research.cycle()['status'] == 'research_needs_attention'
    assert len(rig.instances) == 1 and before == {p.name: p.read_bytes() for p in rig.output.iterdir()}


def test_symlink_escape_is_rejected_before_client(rig, tmp_path):
    rig.configure()
    outside = tmp_path / 'outside'; outside.mkdir()
    try:
        rig.output.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Host does not permit isolated symlink fixtures')
    assert research.cycle()['status'] == 'research_needs_attention'
    assert not rig.instances and not list(outside.iterdir())


def test_close_error_retains_requestful_gate_and_lower_client_cap(rig, monkeypatch):
    rig.configure()
    original = sources.Client
    def existing_client(*args):
        client = original(*args); client.batch_limit = 2
        close = client.close
        def failed_close():
            close(); raise RuntimeError('Isolated close failure')
        client.close = failed_close
        return client
    monkeypatch.setattr(sources, 'Client', existing_client)
    result = research.cycle()
    assert result['requests'] == 2 and result['status'] == 'research_needs_attention'
    assert rig.instances[0].closed and rig.instances[0].batch_limit == 2
    assert json.loads((rig.output / 'backend-last-pass.json').read_text())['status'] == 'research_needs_attention'
    assert research.cycle()['status'] == 'not_due' and len(rig.instances) == 1


def source_owner(rig, monkeypatch, normal_calls):
    from services import selling_discovery_worker
    monkeypatch.setattr(discovery, 'root', lambda: rig.archive / 'discovery')
    monkeypatch.setattr(discovery, 'now', lambda: rig.clock[0])
    monkeypatch.setattr(discovery, 'sync_catalog', lambda: {'status': 'caught_up', 'scanned': 0, 'skipped': 0})
    monkeypatch.setattr(discovery, 'sync_watchlist', lambda: None)
    def normal(_identity):
        normal_calls.append('discovery')
        return {'requests': 9, 'status': 'updated'}
    monkeypatch.setattr(sources, 'refresh_sources', normal)
    return selling_discovery_worker


@pytest.mark.parametrize('research_calls', [0, 40])
def test_existing_before_native_turn_and_discovery_fallback(rig, monkeypatch, research_calls):
    calls = []
    source_owner(rig, monkeypatch, calls)
    def count_turn():
        calls.append('research')
        return {'status': 'fixture', 'requests': research_calls}
    monkeypatch.setattr(research, 'cycle', count_turn)
    async def native(*_args):
        calls.append('native'); return 'completed'
    installed = rig.native / 'versions/fixture/scripts'; installed.mkdir(parents=True)
    (installed / 'keyword_feed.py').write_text('')
    python = rig.native / 'venv/Scripts/python.exe'; python.parent.mkdir(parents=True); python.write_text('')
    (rig.native / 'installation.json').write_text(json.dumps({'code_root': str(installed.parent),
        'python': str(python), 'scheduler_owner': 'etgen_backend', 'schedule_minutes': 15}))
    worker = feed.AppKeywordFeed(rig.native, runner=native, clock=lambda: 0, between_cycles=feed.between_native_cycles)
    asyncio.run(worker.tick())
    assert calls == (['research', 'native'] if research_calls else ['research', 'discovery', 'native'])
    assert worker.next_tick == 900 and worker.state['last_outcome'] == 'completed'
    assert worker.state['review_history_counts']['requests'] == research_calls


def test_minute_worker_and_hook_share_requestful_finish_gate(rig, monkeypatch):
    rig.configure()
    normal = []
    owner = source_owner(rig, monkeypatch, normal)
    first = owner.cycle()
    assert first['requests'] == 40 and not normal
    with discovery.connect() as con:
        retry = con.execute("SELECT value FROM control WHERE name='source_pass_after'").fetchone()[0]
    assert retry == (rig.clock[0] + timedelta(seconds=900)).isoformat()
    rig.clock[0] += timedelta(seconds=60)
    assert owner.cycle()['requests'] == 0
    asyncio.run(feed.between_native_cycles())
    assert len(rig.instances) == 1 and len(rig.calls) == 40 and not normal
    rig.clock[0] += timedelta(seconds=840)
    assert owner.cycle()['requests'] == 2
    assert len(rig.instances) == 2 and not normal


def test_active_research_not_due_reserves_exact_shared_retry(rig, monkeypatch):
    retry = rig.clock[0] + timedelta(seconds=87)
    normal = []
    owner = source_owner(rig, monkeypatch, normal)
    monkeypatch.setattr(research, 'cycle', lambda: {'requests': 0, 'status': 'not_due', 'retry_at': retry.isoformat()})
    result = owner.cycle()
    assert result['requests'] == 0 and not normal
    with discovery.connect() as con:
        assert con.execute("SELECT value FROM control WHERE name='source_pass_after'").fetchone()[0] == retry.isoformat()


@pytest.mark.parametrize('status', ['disabled', 'complete', 'halted', 'authorization_unverified'])
def test_terminal_or_disabled_research_preserves_normal_source_behavior(rig, monkeypatch, status):
    normal = []
    owner = source_owner(rig, monkeypatch, normal)
    monkeypatch.setattr(research, 'cycle', lambda: {'requests': 0, 'status': status})
    assert owner.cycle()['requests'] == 9 and normal == ['discovery']


@pytest.mark.parametrize('status', ['native_collector_running', 'paused'])
def test_busy_research_retries_next_minute_without_normal_calls(rig, monkeypatch, status):
    normal = []
    owner = source_owner(rig, monkeypatch, normal)
    monkeypatch.setattr(research, 'cycle', lambda: {'requests': 0, 'status': status})
    assert owner.cycle()['requests'] == 0 and not normal
    with discovery.connect() as con:
        assert con.execute("SELECT value FROM control WHERE name='source_pass_after'").fetchone()[0] == (rig.clock[0] + timedelta(seconds=60)).isoformat()


def test_hook_and_background_worker_dispatch_cannot_overlap(rig, monkeypatch):
    rig.configure(plan_fixture(size=2, reuses=0))
    normal = []
    owner = source_owner(rig, monkeypatch, normal)
    started, release = threading.Event(), threading.Event()
    def action(client, *_args):
        if not client.requests:
            started.set()
            assert release.wait(timeout=5)
    rig.action[0] = action
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(owner.cycle)
        assert started.wait(timeout=5)
        try:
            assert asyncio.run(feed.between_native_cycles()) is None
            assert len(rig.instances) == 1
        finally:
            release.set()
        assert pending.result(timeout=5)['requests'] == 2
    assert len(rig.calls) == 2 and not normal


@pytest.mark.parametrize('terminal', ['complete', 'halted'])
def test_terminal_pass_finish_gate_survives_old_global_prereservation(rig, monkeypatch, terminal):
    rig.configure(plan_fixture(size=1, reuses=0))
    normal = []
    owner = source_owner(rig, monkeypatch, normal)
    started = rig.clock[0]
    def delayed(client, *_args):
        rig.clock[0] += timedelta(seconds=30)
        if terminal == 'halted':
            client.requests += 1
            raise sources.SourceUnavailable('access_denied', 403)
    rig.action[0] = delayed
    assert owner.cycle()['requests'] == 1
    finished = rig.clock[0]
    # Simulate a crash/failure after the collector persisted its finish gate,
    # before the shared source owner's initial start-time reservation changed.
    with discovery.connect() as con:
        con.execute('INSERT OR REPLACE INTO control VALUES(?,?)',
                    ('source_pass_after', (started + timedelta(seconds=900)).isoformat()))
    rig.clock[0] = started + timedelta(seconds=910)
    result = owner.cycle()
    assert result['requests'] == 0 and result['review_history_counts']['status'] == 'not_due'
    assert not normal and len(rig.instances) == 1
    with discovery.connect() as con:
        assert con.execute("SELECT value FROM control WHERE name='source_pass_after'").fetchone()[0] == (finished + timedelta(seconds=900)).isoformat()
