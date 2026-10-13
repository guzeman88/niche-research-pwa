from datetime import datetime, timedelta, timezone
import json
import sqlite3
import pytest
from pipeline import keyword_database as db
from services import feed_optimization as opt
from services import feed_request_budget as budget
from services.feed_google import import_package
from services.product_validation import digest


@pytest.fixture
def research(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'research.sqlite')
    db.init_db()
    return db


def test_request_budget_counts_pages_failures_and_interruptions(research):
    quota = {'limit_per_day': 100, 'remaining_today': 99}
    with research._conn() as con:
        first = budget.claim(con, quota, 'batch', 2)
    with research._conn() as con:
        second = budget.claim(con, quota, 'batch', 2)
        assert second > first
    with pytest.raises(budget.CollectionDeferred):
        with research._conn() as con: budget.claim(con, quota, 'batch', 2)
    with research._conn() as con:
        assert con.execute('SELECT count(*) FROM feed_etsy_requests').fetchone()[0] == 2
    with pytest.raises(budget.CollectionDeferred):
        with research._conn() as con: budget.claim(con, quota, 'next', 2, daily_limit=2)
    with research._conn() as con:
        assert con.execute('SELECT count(*) FROM feed_etsy_requests').fetchone()[0] == 2


def test_persisted_backoff_and_reserved_quota_survive_restart(research):
    import time
    at = datetime.now(timezone.utc)
    quota = {'limit_per_day': 100, 'remaining_today': 20, 'captured_at': at.isoformat()}
    with research._conn() as con:
        con.execute("INSERT INTO feed_etsy_requests(batch_id,attempted_at,status,quota_json) VALUES('old',?,'200',?)", (at.isoformat(), json.dumps(quota)))
    with pytest.raises(budget.CollectionDeferred, match='reserve'):
        with research._conn() as con: budget.claim(con, {}, 'new', 10)
    with research._conn() as con:
        assert budget.claim(con, {}, 'probe', 10, at=at + timedelta(hours=2))
    quota['retry_after_until'] = time.time() + 3600
    with research._conn() as con:
        con.execute("UPDATE feed_etsy_requests SET quota_json=? WHERE batch_id='old'", (json.dumps(quota),))
    with pytest.raises(budget.CollectionDeferred, match='backoff'):
        with research._conn() as con: budget.claim(con, {}, 'restart', 10)


def test_idle_lane_capacity_is_reallocated_without_bypassing_cooldowns(research, monkeypatch):
    monkeypatch.setenv('FEED_MAX_COLLECTION', '1')
    for i in range(30): research.add_seed(f'teacher mug {i}')
    with research._conn() as con:
        opt.rebuild_candidates(con)
        batch = opt.next_batch(con, 20)
        assert len(batch) == 20
        for kw in batch:
            for provider in ('etsy_open_api', 'google_suggest'):
                opt.record_attempt(con, provider, kw, 'completed', 10, datetime.now(timezone.utc).isoformat())
        assert not set(batch).intersection(opt.next_batch(con, 20))
        assert con.execute('SELECT count(*) FROM seeds').fetchone()[0] == 30


def test_paginated_samples_deduplicate_and_keep_success_before_defer(monkeypatch):
    from adapters.research.etsy_open_api import EtsyOpenAPIClient
    client = EtsyOpenAPIClient()
    monkeypatch.setattr(client, 'is_configured', lambda: True)
    calls = []
    def get(_path, params):
        calls.append(params['offset'])
        if params['offset'] == 4: raise budget.CollectionDeferred('budget')
        identifiers = [1, 2] if params['offset'] == 0 else [2, 3]
        return {'count': 10, 'results': [{'listing_id': n, 'price': {'amount': 1500, 'divisor': 100, 'currency_code': 'USD'}} for n in identifiers]}
    monkeypatch.setattr(client, '_get', get)
    try:
        result = client.search_listings('teacher mug', limit=2, pages=3)
        assert calls == [0, 2, 4]
        assert [r.listing_id for r in result.listings] == ['1', '2', '3']
        assert result.sample_metadata['truncated']
        assert result.total_listing_count == 10
    finally: client.close()


def test_google_500_keyword_package_is_atomic_and_idempotent(research):
    keywords = [f'teacher mug {i}' for i in range(500)]
    payload = {'schema_version': 1, 'source': 'google_ads_keyword_planner',
               'collected_at': datetime.now(timezone.utc).isoformat(), 'requested_keywords': keywords,
               'signals': [{'keyword': k, 'monthly_searches': None, 'metadata': {}} for k in keywords]}
    package = {'payload': payload, 'sha256': digest(payload)}
    with research._conn() as con:
        assert import_package(con, package)['requested'] == 500
        assert import_package(con, package)['duplicate']
        assert con.execute('SELECT count(*) FROM feed_provider_attempts').fetchone()[0] == 500
        assert con.execute('SELECT count(*) FROM keyword_observations').fetchone()[0] == 0


def test_deferred_scheduler_does_not_save_false_empty_scan(research, monkeypatch):
    from pipeline.autonomous_scheduler import AutonomousScheduler
    worker = AutonomousScheduler(mode='continuous', batch_size=2, skip_scraper=True)
    monkeypatch.setattr(db, 'get_next_batch', lambda **_kw: ['teacher mug', 'coder mug'])
    def defer(_kw): raise budget.CollectionDeferred('reserve')
    monkeypatch.setattr(worker, '_scan_and_expand', defer)
    monkeypatch.setattr(worker, '_save_state', lambda **_kw: None)
    result = worker.run_batch_once(batch_size=2, run_discovery=False)
    assert result['status'] == 'completed' and result['keywords_scanned'] == 0
    assert result['deferred_reason'] == 'provider_budget_or_backoff'
    assert result['errors'] == []
    with research._conn() as con:
        assert con.execute('SELECT count(*) FROM scans').fetchone()[0] == 0


def test_raw_response_archive_retains_exact_values(research):
    import gzip
    quota = {'limit_per_day': 5000, 'remaining_today': 4900}
    with research._conn() as con:
        identity = budget.claim(con, quota, 'archive', 2)
    raw = {'count': 2, 'results': [{'listing_id': 5, 'price': {'amount': 1250, 'divisor': 100}}]}
    budget.finish_request(identity, '200', quota, '/listings/active', {'offset': 100}, raw)
    with research._conn() as con:
        row = con.execute('SELECT * FROM feed_etsy_requests').fetchone()
        assert json.loads(gzip.decompress(row['response_gzip'])) == raw
        assert json.loads(row['request_json'])['params']['offset'] == 100
        assert con.execute('SELECT max(version) FROM schema_version').fetchone()[0] == 19


def test_explicit_verification_can_bypass_queue_with_maximum_policy(research, monkeypatch):
    from adapters.research import etsy_open_api as api
    from adapters.research.etsy_search_scraper import EtsySearchResult
    from pipeline.stages import niche_research as stage
    monkeypatch.setenv('FEED_MAX_COLLECTION', '1')
    monkeypatch.setenv('FEED_OPTIMIZED_QUEUE', '0')
    monkeypatch.setattr(api, 'is_etsy_open_api_configured', lambda: True)
    monkeypatch.setattr(stage, '_record_provider_attempt', lambda **_kw: None)
    calls = []
    def search(_self, keyword, limit=100, **_kw):
        calls.append(keyword)
        return EtsySearchResult(keyword=keyword, total_listing_count=0)
    monkeypatch.setattr(api.EtsyOpenAPIClient, 'search_listings', search)
    assert stage._run_etsy_open_api_search(['teacher mug'], lambda _msg: None) == []
    assert calls == ['teacher mug']


def test_maximum_scheduler_does_not_wait_90_seconds_before_first_etsy_reply(research, monkeypatch):
    from pipeline.autonomous_scheduler import AutonomousScheduler
    monkeypatch.setenv('FEED_MAX_COLLECTION', '1')
    monkeypatch.setenv('SCHEDULER_RESEARCH_ADAPTERS', 'etsy_open_api,google_suggest')
    worker = AutonomousScheduler(mode='continuous', skip_scraper=False)
    assert worker._scan_interval_seconds() == 1.0
