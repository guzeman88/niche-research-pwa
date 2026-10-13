from datetime import datetime, timedelta, timezone
import json
import sqlite3
import pytest
from pipeline import keyword_database as db
from services import feed_optimization as opt
from services.collector_bridge import import_incremental
from services.feed_google import import_package
from services.product_validation import digest


@pytest.fixture
def research(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'native.sqlite')
    db.init_db()
    return db


def test_active_shortlist_preserves_weak_seeds_and_lane_budgets(research):
    weak = 'december gift sets micro-business identity apparel'
    research.add_seed(weak)
    for index in range(25):
        research.add_seed(f'funny teacher mug {index}')
    with research._conn() as con:
        opt.rebuild_candidates(con, limit=15)
        before = con.execute('SELECT count(*) FROM seeds').fetchone()[0]
        active = con.execute("SELECT keyword FROM feed_candidates WHERE tier='active'").fetchall()
        for row in active[:8]:
            con.execute('INSERT INTO keyword_collection_state VALUES(?,?,?,?,?,?,?,?,?)', (row['keyword'], '2020-01-01', 'unverified', None, None, None, '[]', None, '2020-01-01'))
            con.execute('INSERT INTO provider_keyword_state VALUES(?,?,?,?,?,?,?)', ('etsy_open_api', row['keyword'], '2020-01-01', None, 'no_data', 0, None))
        batch = opt.next_batch(con, 10)
        refreshed = sum(con.execute('SELECT 1 FROM keyword_collection_state WHERE keyword=?', (kw,)).fetchone() is not None for kw in batch)
        assert refreshed <= 2
        assert len(batch) == 10
        assert weak not in batch
        assert con.execute('SELECT count(*) FROM seeds').fetchone()[0] == before


def test_empty_backoff_failure_backoff_and_provider_independence(research):
    at = datetime.now(timezone.utc)
    for index in range(3):
        research.record_provider_keyword_attempt('etsy_open_api', 'teacher mug', status='no_data', row_count=0, attempted_at=at.isoformat())
    with research._conn() as con:
        row = con.execute('SELECT * FROM feed_provider_cooldowns').fetchone()
        assert row['empty_streak'] == 3
        assert opt.utc(row['next_due']) == at + timedelta(days=28)
        assert not opt.provider_due(con, 'etsy_open_api', 'teacher mug', at)
        assert opt.provider_due(con, 'google_suggest', 'teacher mug', at)
    research.record_provider_keyword_attempt('etsy_open_api', 'teacher mug', status='failed', row_count=0, attempted_at=at.isoformat())
    with research._conn() as con:
        assert opt.utc(con.execute('SELECT next_due FROM feed_provider_cooldowns').fetchone()[0]) == at + timedelta(hours=2)
        report = opt.coverage(con)
        assert report['providers'][0]['attempts'] == 4
        assert report['providers'][0]['unique_keywords'] == 1
        assert report['providers'][0]['repeated_attempts'] == 3
        assert report['providers'][0]['failed_attempts'] == 1


def test_bridge_keeps_original_and_raw_conflicts_without_native_scan_collision(research, tmp_path):
    source_path = tmp_path / 'original.sqlite'
    with sqlite3.connect(source_path) as source:
        source.execute('CREATE TABLE seeds(keyword TEXT PRIMARY KEY, domain TEXT,source TEXT,added_at TEXT)')
        source.execute("INSERT INTO seeds VALUES('teacher mug','original','manual','2020')")
        source.execute('CREATE TABLE scans(id INTEGER PRIMARY KEY,keyword TEXT,scanned_at TEXT)')
        source.execute("INSERT INTO scans VALUES(1,'teacher mug','2020')")
    research.add_seed('teacher mug', domain='native')
    research.save_scan('teacher mug', {'sources_used': []})
    with research._conn() as con:
        result = import_incremental(con, source_path, limit=100)
        assert result['imported_rows'] == 2
        assert import_incremental(con, source_path, limit=100)['imported_rows'] == 0
        assert con.execute('SELECT domain FROM seeds').fetchone()[0] == 'native'
        assert con.execute('SELECT count(*) FROM scans').fetchone()[0] == 1
        assert json.loads(con.execute("SELECT payload FROM feed_import_records WHERE table_name='seeds'").fetchone()[0])['domain'] == 'original'
    with sqlite3.connect(source_path) as source:
        assert source.execute('SELECT count(*) FROM seeds').fetchone()[0] == 1
        source.execute('DELETE FROM scans')
    with pytest.raises(ValueError, match='HistoryChanged'):
        with research._conn() as con:
            import_incremental(con, source_path, limit=100)


def test_bridge_rolls_back_archive_and_checkpoint_on_projection_failure(research, tmp_path, monkeypatch):
    source_path = tmp_path / 'original.sqlite'
    with sqlite3.connect(source_path) as source:
        source.execute('CREATE TABLE seeds(keyword TEXT PRIMARY KEY)')
        source.execute("INSERT INTO seeds VALUES('mug')")
    from services import collector_bridge
    def fail(*_):
        raise sqlite3.OperationalError('Interrupted projection')
    monkeypatch.setattr(collector_bridge, '_project', fail)
    with pytest.raises(sqlite3.OperationalError):
        with research._conn() as con:
            import_incremental(con, source_path, limit=100)
    with research._conn() as con:
        assert con.execute('SELECT count(*) FROM feed_import_records').fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM feed_import_checkpoints').fetchone()[0] == 0


def test_google_atomic_idempotence_unknowns_and_close_variant_volume(research):
    at = datetime.now(timezone.utc).isoformat()
    payload = {'schema_version': 1, 'source': 'google_ads_keyword_planner', 'collected_at': at,
               'requested_keywords': ['teacher mug', 'teacher mugs', 'rare mug'], 'geography': 'US',
               'signals': [{'keyword': 'teacher mug', 'monthly_searches': 100, 'metadata': {'close_variants': ['teacher mugs']}},
                           {'keyword': 'rare mug', 'monthly_searches': None, 'metadata': {}}]}
    package = {'payload': payload, 'sha256': digest(payload)}
    with research._conn() as con:
        assert not import_package(con, package)['duplicate']
        assert import_package(con, package)['duplicate']
        assert con.execute("SELECT count(*) FROM keyword_observations WHERE metric='monthly_searches'").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM feed_provider_attempts").fetchone()[0] == 3
        assert con.execute("SELECT status FROM provider_keyword_state WHERE keyword='rare mug'").fetchone()[0] == 'no_data'
        due = con.execute("SELECT next_due FROM feed_provider_cooldowns WHERE keyword='rare mug'").fetchone()[0]
        assert opt.utc(due) >= opt.utc(at) + timedelta(days=28)
    payload['signals'][0]['monthly_searches'] = -1
    invalid = {'payload': payload, 'sha256': digest(payload)}
    with pytest.raises(ValueError):
        with research._conn() as con:
            import_package(con, invalid)
    with research._conn() as con:
        assert con.execute('SELECT count(*) FROM feed_google_packages').fetchone()[0] == 1


def test_marketplace_shortlist_import_is_idempotent_and_preserves_rounding(research):
    from services.feed_market import import_observation
    research.add_seed('teacher mug')
    observation = {'keyword': 'teacher mug', 'observed_at': '2026-10-12',
                   'period_start': '2026-09-12', 'period_end': '2026-10-11',
                   'searches': 100, 'listings': 5900, 'geography': 'unspecified',
                   'source_note': '5.9k approximate (rounded provider display)'}
    raw = {'collected_at': '2026-10-12T15:00:00+00:00'}
    with research._conn() as con:
        opt.rebuild_candidates(con)
        assert not import_observation(con, observation, raw)['duplicate']
        assert import_observation(con, observation, raw)['duplicate']
        rows = con.execute('SELECT metadata_json FROM keyword_observations').fetchall()
        assert len(rows) == 2
        assert all(json.loads(r[0])['rounded_listings'] for r in rows)


def test_v18_upgrade_preserves_all_existing_research(research):
    research.add_seed('legacy mug')
    research.save_scan('legacy mug', {'sources_used': []})
    with research._conn() as con:
        before = {table: con.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in ('seeds', 'scans', 'evidence_collection_runs')}
        con.execute('DELETE FROM schema_version')
        con.execute('INSERT INTO schema_version VALUES(17)')
    research.init_db()
    with research._conn() as con:
        assert before == {table: con.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in before}


def test_etsy_reserve_guard_prevents_requests(monkeypatch):
    from adapters.research import etsy_open_api
    monkeypatch.setenv('FEED_OPTIMIZED_QUEUE', '1')
    monkeypatch.setattr(etsy_open_api, 'etsy_rate_limit_snapshot', lambda: {'limit_per_day': 100, 'remaining_today': 20})
    client = etsy_open_api.EtsyOpenAPIClient()
    monkeypatch.setattr(client._client, 'get', lambda *_a, **_kw: pytest.fail('Quota reserve must not send another request'))
    try:
        with pytest.raises(etsy_open_api.EtsyOpenAPIError, match='reserve'):
            client._get('/listings/active')
    finally:
        client.close()


def test_imported_suggestions_prevent_redundant_calls_without_native_attempt(research):
    at = datetime.now(timezone.utc)
    research.add_seed('teacher mug')
    with research._conn() as con:
        con.execute('INSERT INTO keyword_suggestions(parent_keyword,suggestion,source,query,position,observed_at) VALUES(?,?,?,?,?,?)', ('teacher mug', 'funny teacher mug', 'google_suggest', 'teacher mug', 1, at.isoformat()))
        assert not opt.provider_due(con, 'google_suggest', 'teacher mug', at)
        assert opt.provider_due(con, 'google_suggest', 'teacher mug', at + timedelta(days=15))
        assert opt.provider_due(con, 'etsy_open_api', 'teacher mug', at)
        assert con.execute('SELECT count(*) FROM feed_provider_attempts').fetchone()[0] == 0


def test_supporting_refresh_preserves_fresh_verified_market_state_and_attempt_history(research, monkeypatch):
    monkeypatch.setenv('FEED_OPTIMIZED_QUEUE', '1')
    research.add_seed('teacher mug'); at = datetime.now(timezone.utc).isoformat()
    with research._conn() as con:
        con.execute('INSERT INTO keyword_collection_state VALUES(?,?,?,?,?,?,?,?,?)', ('teacher mug', at, 'verified', 1000, 20, 25, '["etsy_open_api"]', None, at))
    research.save_scan('teacher mug', {'sources_used': ['google_suggest']})
    with research._conn() as con:
        state = con.execute('SELECT * FROM keyword_collection_state').fetchone()
        assert state['last_collected_at'] == at
        assert state['evidence_status'] == 'verified'
        assert state['listing_count'] == 1000
        assert con.execute('SELECT scan_status FROM scans').fetchone()[0] == 'signals'
        con.execute("UPDATE keyword_collection_state SET last_collected_at='2020-01-01'")
    research.save_scan('teacher mug', {'sources_used': ['google_suggest']})
    with research._conn() as con:
        assert con.execute('SELECT evidence_status FROM keyword_collection_state').fetchone()[0] == 'unverified'
        assert con.execute('SELECT count(*) FROM scans').fetchone()[0] == 2
