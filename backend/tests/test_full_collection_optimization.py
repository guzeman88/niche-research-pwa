"""Native capacity, pooled transport, source isolation and idempotent batch mirroring."""
from datetime import datetime, timezone
import json
import httpx
import pytest
from pipeline import keyword_database as db
from services import feed_optimization as opt
from services import supabase_evidence_sync as sync
from services import collection_transport as pool
from adapters.research.google_suggest import GoogleSuggestAdapter
from pipeline.autonomous_scheduler import AutonomousScheduler


@pytest.fixture
def research(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'proof.sqlite')
    db.init_db()
    return db


@pytest.mark.parametrize('size', [100, 170])
def test_native_batch_collects_more_than_fifty_with_durable_quota_mode(research, monkeypatch, size):
    monkeypatch.setenv('FEED_MAX_COLLECTION', '1')
    monkeypatch.setenv('EVIDENCE_DURABILITY_MODE', 'local-outbox')
    worker = AutonomousScheduler(mode='continuous', skip_scraper=True)
    monkeypatch.setattr(db, 'get_next_batch', lambda **_kw: [f'mug {i}' for i in range(size)])
    calls = []
    monkeypatch.setattr(worker, '_scan_and_expand', lambda kw: calls.append(kw) or 0)
    monkeypatch.setattr(worker, '_save_state', lambda **_kw: None)
    result = worker.run_batch_once(batch_size=size, run_discovery=False, respect_rate_limit=False)
    assert result['requested'] == size and result['keywords_scanned'] == size
    assert len(set(calls)) == size


def test_native_defer_requires_persistent_local_mode(research, monkeypatch):
    identity = db.start_evidence_collection('etsy_open_api', {'keyword': 'teacher mug'})
    monkeypatch.setenv('FEED_BATCHED_MIRROR', '1')
    calls = []
    monkeypatch.setattr(sync, 'sync_collection_run', lambda _id: calls.append(_id) or {'configured': True, 'status': 'failed'})
    monkeypatch.delenv('EVIDENCE_DURABILITY_MODE', raising=False)
    with pytest.raises(sync.DurableEvidenceSyncError):
        sync.require_collection_sync(identity)
    monkeypatch.setenv('EVIDENCE_DURABILITY_MODE', 'local-outbox')
    assert sync.require_collection_sync(identity)['locally_preserved']
    assert calls == [identity]


def test_group_mirror_failure_replays_without_false_local_ack(research, monkeypatch):
    monkeypatch.setattr(sync, 'is_configured', lambda: True)
    db.add_seed('teacher mug')
    ids = [db.start_evidence_collection('etsy_open_api', {'keyword': 'teacher mug'}) for _ in range(2)]
    for identity in ids:
        db.finish_evidence_collection(identity, 'completed', 0)
    calls = []; fail = [True]
    def upsert(table, conflict, rows):
        calls.append((table, rows))
        if fail[0] and table == 'evidence_collection_runs' and rows and rows[0].get('durable_sync_status') == 'synced':
            raise OSError('Lost acknowledgement')
    monkeypatch.setattr(sync, '_upsert', upsert)
    assert sync.sync_collection_runs(ids)['status'] == 'failed'
    with db._conn() as con:
        assert con.execute("SELECT count(*) FROM evidence_collection_runs WHERE durable_sync_status='synced'").fetchone()[0] == 0
    fail[0] = False
    assert sync.sync_collection_runs(ids)['status'] == 'synced'
    with db._conn() as con:
        assert con.execute("SELECT count(*) FROM evidence_collection_runs WHERE durable_sync_status='synced'").fetchone()[0] == 2
    assert all(len(rows) <= 1 for table, rows in calls if table == 'keyword_seeds')


def test_cohort_mirror_drains_more_than_one_hundred_runs(research, monkeypatch):
    monkeypatch.setenv('FEED_BATCHED_MIRROR', '1'); monkeypatch.setenv('EVIDENCE_DURABILITY_MODE', 'local-outbox')
    monkeypatch.setattr(sync, 'is_configured', lambda: True)
    monkeypatch.setattr(sync, '_upsert', lambda *_args: None)
    for i in range(105):
        identity = db.start_evidence_collection('etsy_open_api', {'keyword': f'teacher mug {i}'})
        db.finish_evidence_collection(identity, 'no_data', 0)
    result = sync.retry_collection_outbox(500)
    assert result == {'synced': 105, 'failed': 0, 'pending': 0}


def test_pairing_and_provider_lanes_keep_independent_cooldowns(research, monkeypatch):
    monkeypatch.setenv('FEED_MAX_COLLECTION', '1')
    for kw in ['plain teacher mug', 'paired teacher mug']:
        db.add_seed(kw)
    now = datetime.now(timezone.utc).isoformat()
    db.record_keyword_observation(keyword='paired teacher mug', source='google_ads_keyword_planner', metric='monthly_searches', value=100, unit='searches_per_month', observed_at=now)
    db.record_provider_keyword_attempt('etsy_open_api', 'plain teacher mug', status='completed', row_count=1, attempted_at=now)
    with db._conn() as con:
        opt.rebuild_candidates(con)
        monkeypatch.setenv('FEED_COLLECTION_LANE', 'competition')
        assert opt.next_batch(con, 1) == ['paired teacher mug']
        monkeypatch.setenv('FEED_COLLECTION_LANE', 'discovery')
        assert set(opt.next_batch(con, 10)) == {'plain teacher mug', 'paired teacher mug'}


def test_pooled_clients_survive_wrappers_and_close_only_at_batch_end(monkeypatch):
    from adapters.research.etsy_open_api import EtsyOpenAPIClient
    with pool.pooled_transports():
        first, second = EtsyOpenAPIClient(), EtsyOpenAPIClient()
        assert first._client is second._client
        first.close(); assert not second._client.is_closed
        client = second._client
    assert client.is_closed and pool.transport('etsy') is None


def test_suggest_preserves_partial_results_and_reuses_transport(research, monkeypatch):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=['query', ['teacher coffee mug']]) if len(requests) == 1 else httpx.Response(500)
    client = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(pool, 'transport', lambda name: client)
    adapter = GoogleSuggestAdapter(request_delay=0)
    rows = adapter.search('teacher mug')
    assert len(rows) == 1 and len(requests) == 4
    assert rows[0].metadata['capture_status'] == 'partial'
    assert rows[0].monthly_searches is None
    client.close()


def test_suggest_rate_limit_persists_global_backoff_without_empty_evidence(research, monkeypatch):
    monkeypatch.setenv('FEED_MAX_COLLECTION', '1')
    client = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(429, headers={'retry-after': '3600'})))
    monkeypatch.setattr(pool, 'transport', lambda name: client)
    with pytest.raises(RuntimeError, match='SuggestIncompleteResponse'):
        GoogleSuggestAdapter(request_delay=0).search('teacher mug')
    with db._conn() as con:
        assert not opt.provider_available(con, 'google_suggest')
        assert not opt.provider_due(con, 'google_suggest', 'other mug')
        assert opt.provider_due(con, 'etsy_open_api', 'other mug')
    client.close()


def test_shared_google_variants_count_coverage_without_copying_volume(research):
    now = datetime.now(timezone.utc).isoformat()
    db.record_keyword_observation(keyword='teacher mug', source='google_ads_keyword_planner', metric='monthly_searches', value=100, unit='searches_per_month', observed_at=now, metadata={'close_variants':['teacher mugs']})
    with db._conn() as con:
        direct, shared = opt.google_monthly_coverage(con)
        assert direct == {'teacher mug'} and shared == {'teacher mug', 'teacher mugs'}
        assert con.execute("SELECT count(*) FROM keyword_observations WHERE metric='monthly_searches'").fetchone()[0] == 1


def test_separate_lanes_never_inherit_legacy_ninety_second_delay(monkeypatch):
    monkeypatch.setenv('FEED_MAX_COLLECTION', '1')
    monkeypatch.setenv('FEED_COLLECTION_LANE', 'discovery')
    monkeypatch.setenv('SCHEDULER_RESEARCH_ADAPTERS', 'google_suggest')
    worker = AutonomousScheduler(mode='continuous', skip_scraper=True)
    assert worker._scan_interval_seconds() == 1.0
    monkeypatch.setenv('FEED_COLLECTION_LANE', 'competition')
    assert worker._scan_interval_seconds() == 0.0


def test_actual_page_pacing_uses_observed_qps_and_keeps_headroom():
    from adapters.research.etsy_open_api import paced_request_interval_seconds
    assert paced_request_interval_seconds({'limit_per_second':5,'remaining_this_second':4}) == .25
    assert paced_request_interval_seconds({'limit_per_second':5,'remaining_this_second':0}) == 1
    assert paced_request_interval_seconds({}) == 1
    assert paced_request_interval_seconds({'limit_per_second':1}) >= 1


def test_provider_telemetry_uses_existing_mirror_pool(monkeypatch):
    from services.provider_telemetry import record_provider_attempt
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r.url.path) or httpx.Response(201)))
    monkeypatch.setattr(pool, 'transport', lambda _name: client)
    monkeypatch.setenv('SUPABASE_URL', 'http://127.0.0.1:18000')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'test-only')
    record_provider_attempt(provider='etsy_open_api',operation='search',status='completed',
                            started_at=datetime.now(timezone.utc),keyword_count=1,row_count=100)
    assert len(calls) == 2 and not client.is_closed
    client.close()
