"""Isolated contract/recovery tests. No real provider, ledger or account is used."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import pytest
from services.sales_intelligence import store, registry, ingestion, consensus, features, training, worker, quotas, service

UTC = timezone.utc


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setenv('SALES_INTELLIGENCE_ROOT', str(tmp_path / 'archive'))
    monkeypatch.setenv('APP_KEYWORD_FEED_ROOT', str(tmp_path / 'native'))
    monkeypatch.setenv('VALIDATION_DB_PATH', str(tmp_path / 'ledger.sqlite'))
    store.counts()
    at = store.now()
    grants = {source: {'reference': 'Isolated test fixture, not actual permission', 'account_ref': 'fixture-account',
        'issued_at': (at - timedelta(days=500)).isoformat(), 'expires_at': (at + timedelta(days=100)).isoformat(),
        'free_only': True, 'capabilities': ['storage', 'comparison', 'training', 'export', 'automated'],
        'quota': {'period': 'daily', 'timezone': 'UTC', 'limit': 2}} for source, *_ in registry.SEEDS}
    (store.root() / 'access.json').write_text(json.dumps(grants))
    return tmp_path


def reading(source='muadzo', value=20, listing='123', **kwargs):
    at = store.now() - timedelta(minutes=5)
    return {'source_id': source, 'listing_id': listing, 'metric': 'estimated_sales', 'value': value,
            'basis': 'period', 'unit': 'purchases', 'period_start': (at - timedelta(days=30)).isoformat(),
            'period_end': at.isoformat(), 'captured_at': at.isoformat(), 'available_at': at.isoformat(),
            'source_ref': 'Isolated provider export fixture', **kwargs}


def packet(rows, source='muadzo'):
    return {'source_id': source, 'format': 'json', 'content': json.dumps(rows)}


def save(rows, source='muadzo'):
    data = packet(rows, source)
    preview = ingestion.preview(data)
    return ingestion.commit({**data, 'expected_fingerprint': preview['fingerprint']})


def aligned(sources, values, **kwargs):
    first = reading(**kwargs)
    for source, value in zip(sources, values):
        save([{**first, 'source_id': source, 'value': value}], source)
    return first


def test_registry_and_capability_expiry(archive):
    assert len(registry.sources()) == 24
    assert registry.permission('muadzo', 'training')
    grants = registry.grants()
    grants['muadzo']['expires_at'] = (store.now() - timedelta(seconds=1)).isoformat()
    (store.root() / 'access.json').write_text(json.dumps(grants))
    assert not registry.permission('muadzo', 'training')
    assert registry.source('muadzo')['capabilities']['training'] is False
    with pytest.raises(ValueError):
        registry.source('invented_api')


def test_import_idempotence_zero_and_original_artifact(archive):
    value = reading(value=0)
    assert save([value])['inserted'] == 1
    assert save([value])['duplicates'] == 1
    with store.database() as con:
        report = consensus.build(con, '123')
        assert report['cohorts'][0]['center'] == 0
        artifact = con.execute('SELECT payload FROM artifacts').fetchone()[0]
        assert json.loads(artifact)['content'] == json.dumps([value])


@pytest.mark.parametrize('patch', [
    {'value': True}, {'value': float('inf')}, {'value': -1}, {'value': None},
    {'unit': 'currency'}, {'basis': 'lifetime'}, {'period_end': None},
    {'captured_at': datetime.now().isoformat()}, {'available_at': (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    {'listing_id': 'https://evil.example/12'}, {'metadata': {'email': 'forbidden fixture'}},
])
def test_invalid_semantics_cannot_commit(archive, patch):
    data = packet([reading(**patch)])
    result = ingestion.preview(data)
    assert result['rejected']
    with pytest.raises(ValueError):
        ingestion.commit({**data, 'expected_fingerprint': result['fingerprint']})
    assert store.counts()['observations'] == 0


def test_no_access_cannot_be_enabled_by_browser_pause(archive):
    (store.root() / 'access.json').unlink()
    registry.pause('muadzo', False)
    data = packet([reading()])
    result = ingestion.preview(data)
    assert not result['can_commit']
    with pytest.raises(ValueError, match='evidence'):
        ingestion.commit({**data, 'expected_fingerprint': result['fingerprint']})


def test_preview_fingerprint_and_atomic_corrections(archive):
    value = reading()
    save([value])
    with store.database() as con:
        identity = con.execute('SELECT id FROM observations').fetchone()[0]
    fixed = {**value, 'value': 30, 'available_at': (store.now() - timedelta(seconds=2)).isoformat(), 'supersedes': identity}
    save([fixed])
    with store.database() as con:
        assert consensus.build(con, '123')['cohorts'][0]['center'] == 30
        assert consensus.build(con, '123', value['available_at'])['cohorts'][0]['center'] == 20
    bad = {**fixed, 'supersedes': '0' * 64, 'value': 12}
    with pytest.raises(ValueError, match='existing'):
        save([bad])
    assert store.counts()['observations'] == 2
    data = packet([reading(value=50)])
    with pytest.raises(ValueError, match='Preview'):
        ingestion.commit({**data, 'expected_fingerprint': 'old'})


def test_robust_consensus_and_duplicate_upstreams(archive):
    original = aligned(['muadzo', 'hive', 'ehunt', 'erank', 'rankhero'], [12, 18, 20, 22, 180])
    with store.database() as con:
        cohort = consensus.build(con, '123')['cohorts'][0]
    assert cohort['mean'] == 50.4
    assert cohort['center'] == 20
    assert cohort['range_kind'] == 'source_disagreement_not_confidence'
    aligned(['etsimator', 'sellfinch'], [500, 500], **{k: original[k] for k in ('period_start', 'period_end', 'captured_at', 'available_at')})
    with store.database() as con:
        cohort = consensus.build(con, '123')['cohorts'][0]
    assert cohort['source_count'] == 7 and cohort['group_count'] == 6
    assert sum(r['weight'] for r in cohort['readings'] if r['group'] == 'etsimator') == 1


def test_units_windows_bounds_and_staleness_stay_separate(archive):
    first = reading()
    save([first])
    save([{**first, 'source_id': 'hive', 'unit': 'units', 'value': 200}], 'hive')
    save([{**first, 'source_id': 'ehunt', 'precision': 'lower_bound', 'value': 999}], 'ehunt')
    old = {**first, 'source_id': 'erank', 'provider_updated_at': (store.now() - timedelta(days=9)).isoformat()}
    save([old], 'erank')
    with store.database() as con:
        report = consensus.build(con, '123')
    assert len(report['cohorts']) == 2
    assert all(c['source_count'] == 1 for c in report['cohorts'])
    assert {r['reason'] for r in report['excluded']} == {'bounded_value_not_point_estimate', 'stale_reference'}


def test_csv_explicit_mapping_does_not_assume_month(archive):
    data = {'source_id': 'ehunt', 'format': 'csv', 'content': 'Listing ID,Monthly Sales\n123,12+\n',
            'value_column': 'monthly_sales', 'basis': 'provider_monthly', 'unit': 'unknown',
            'captured_at': (store.now() - timedelta(minutes=2)).isoformat(), 'available_at': store.now().isoformat(), 'source_ref': 'Fixture CSV'}
    report = ingestion.preview(data)
    assert report['sample'][0]['basis'] == 'provider_monthly'
    assert report['sample'][0]['precision'] == 'lower_bound'
    assert report['sample'][0]['unit'] == 'unknown'
    with pytest.raises(ValueError, match='buyer'):
        ingestion.preview({**data, 'content': 'Listing ID,buyer_email\n123,test\n'})


def test_quota_reservations_survive_restart_and_reset(archive):
    at = store.now()
    with store.database(True) as con:
        quotas.reserve(con, 'muadzo', 'first', at=at)
    with store.database(True) as con:
        assert quotas.reserve(con, 'muadzo', 'second', at=at)['remaining'] == 0
    with store.database(True) as con, pytest.raises(ValueError, match='exhausted'):
        quotas.reserve(con, 'muadzo', 'third', at=at)
    with store.database(True) as con:
        assert quotas.reserve(con, 'muadzo', 'tomorrow', at=at + timedelta(days=1))['remaining'] == 1


def test_features_exclude_future_and_teacher_values(archive):
    at = store.now() - timedelta(days=1)
    meta = {'listing_id': '123', 'title': 'Fixture planner', 'shop': 'fixture-shop', 'source_ref': 'Fixture metadata',
            'captured_at': at.isoformat(), 'available_at': at.isoformat(), 'favorites': 10, 'price': 5}
    with store.database(True) as con:
        store.add_metadata(con, meta)
        first = features.snapshot(con, '123', at.isoformat())
        store.add_metadata(con, {**meta, 'captured_at': (at + timedelta(hours=1)).isoformat(), 'available_at': (at + timedelta(hours=1)).isoformat(), 'favorites': 9999})
        again = features.snapshot(con, '123', at.isoformat())
    assert first['fingerprint'] == again['fingerprint']
    assert not any('sales' in key or 'outcome' in key for key in first['values'])


def test_native_bridge_is_read_only_resumable_and_preserves_originals(archive):
    native = archive / 'native'
    (native / 'data').mkdir(parents=True)
    path = native / 'data/catalog.sqlite'
    source = sqlite3.connect(path)
    source.execute('CREATE TABLE keyword_listing_snapshots(id INTEGER PRIMARY KEY, listing_id TEXT,title TEXT,shop_name TEXT, observed_at TEXT,price REAL,currency_code TEXT,favorites INTEGER,review_count INTEGER)')
    at = (store.now() - timedelta(hours=1)).isoformat()
    source.executemany('INSERT INTO keyword_listing_snapshots VALUES(?,?,?,?,?,?,?,?,?)', [(i, str(i), 'Fixture product', 'Fixture shop', at, 8, 'USD', i, None) for i in range(1, 5)])
    source.commit(); source.close()
    original = path.read_bytes()
    (native / 'installation.json').write_text(json.dumps({'database': str(path)}))
    assert features.sync_catalog(limit=2)['inserted'] == 2
    assert features.sync_catalog(limit=2)['inserted'] == 2
    assert features.sync_catalog(limit=2)['inserted'] == 0
    assert original == path.read_bytes()
    assert store.counts()['listings'] == 4


def test_outcomes_cannot_be_provider_references_or_overlap(archive):
    with pytest.raises(Exception):
        ingestion.import_outcomes({'format': 'json', 'content': json.dumps([reading()])})
    at = store.now() - timedelta(days=1)
    actual = {'listing_id': '123', 'shop': 'Fixture shop', 'shop_id': '789', 'period_start': (at - timedelta(days=30)).isoformat(), 'period_end': at.isoformat(),
              'available_at': store.now().isoformat(), 'actual': 0, 'unit': 'purchases', 'source_ref': 'Fixture seller records',
              'attestation': 'Authorized aggregate seller record fixture; no buyer information'}
    data = {'content': json.dumps([actual]), 'format': 'json'}
    check = ingestion.import_outcomes(data)
    assert not check['committed']
    assert ingestion.import_outcomes({**data, 'expected_fingerprint': check['fingerprint']})['committed']
    conflict = {**actual, 'actual': 5}
    check = ingestion.import_outcomes({**data, 'content': json.dumps([conflict])})
    with pytest.raises(ValueError, match='overlap'):
        ingestion.import_outcomes({'content': json.dumps([conflict]), 'expected_fingerprint': check['fingerprint']})


def test_jobs_pause_recovery_and_no_unverified_network(archive):
    job = worker.enqueue('catalog')
    with store.database(True) as con:
        store.set_control(con, 'paused', True)
    assert worker.cycle()['status'] == 'paused'
    with store.database(True) as con:
        store.set_control(con, 'paused', False)
        con.execute("UPDATE jobs SET status='running',lease_until=? WHERE id=?", ((store.now() - timedelta(seconds=1)).isoformat(), job['id']))
    result = worker.cycle()
    assert result['external_requests'] == 0
    with store.database() as con:
        assert con.execute('SELECT status FROM jobs WHERE id=?', (job['id'],)).fetchone()[0] == 'completed'
    assert worker.plan()['external_requests_planned'] == 0


def test_empty_training_and_rollback_are_truthful(archive):
    result = training.fit()
    assert result['status'] == 'insufficient_data'
    assert result['cases'] == 0
    with pytest.raises(ValueError, match='previously'):
        training.rollback()
    assert training.prediction('123')['value'] is None


def test_sql_search_is_literal(archive):
    with store.database(True) as con:
        store.add_metadata(con, {'listing_id': '123', 'title': 'Fixture 100% product', 'shop': 'Fixture',
            'captured_at': store.now().isoformat(), 'available_at': store.now().isoformat(), 'source_ref': 'Fixture'})
    assert service.overview('%')['total'] == 1
    assert service.overview("' OR 1=1 --")['total'] == 0


def test_api_is_private_and_no_store(archive, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setenv('PIPELINE_API_TOKEN', 'fixture-token')
    client = TestClient(app)
    assert client.get('/api/sales-intelligence').status_code == 401
    response = client.get('/api/sales-intelligence/sources', headers={'Authorization': 'Bearer fixture-token'})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    assert len(response.json()['items']) == 24
    assert 'account_ref' not in response.text
    assert client.post('/api/sales-intelligence/sources/muadzo/resume', headers={'Authorization': 'Bearer fixture-token'}).status_code == 200


def test_csv_duplicate_headers_and_ragged_rows_rejected(archive):
    for content in ('Listing ID,listing_id\n123,123\n', 'Listing ID,Monthly Sales\n123,5,6\n'):
        with pytest.raises(ValueError):
            ingestion.preview({'source_id': 'muadzo', 'format': 'csv', 'content': content})


def test_raw_saved_api_bridge_retains_views_and_does_not_import_reviews_as_products(archive):
    import gzip
    native = archive / 'native'
    (native / 'data').mkdir(parents=True)
    path = native / 'data/catalog.sqlite'
    (native / 'installation.json').write_text(json.dumps({'database': str(path)}))
    at = store.now() - timedelta(hours=1)
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE feed_etsy_requests(id INTEGER PRIMARY KEY,attempted_at TEXT,status TEXT,quota_json TEXT,response_gzip BLOB)')
        payload = {'results': [{'listing_id': 123, 'title': 'Fixture saved listing', 'shop_id': 789, 'views': 456,
            'num_favorers': 12, 'quantity': 8, 'listing_type': 'download', 'taxonomy_id': 77,
            'original_creation_timestamp': int((at - timedelta(days=90)).timestamp()), 'price': {'amount': 500, 'divisor': 100, 'currency_code': 'USD'}}]}
        for ident, value in [(1, payload), (2, {'results': [{'listing_id': 123, 'rating': 5, 'review': 'Fixture review'}]})]:
            con.execute('INSERT INTO feed_etsy_requests VALUES(?,?,?,?,?)', (ident, at.isoformat(), '200', '{}', gzip.compress(json.dumps(value).encode())))
    original = path.read_bytes()
    assert features.sync_raw_catalog()['inserted'] == 1
    with store.database() as con:
        vector = features.snapshot(con, '123', store.now().isoformat())
        assert vector['metadata']['views'] == 456
        assert vector['metadata']['price'] == 5
        assert vector['metadata']['title'] == 'Fixture saved listing'
    assert features.sync_raw_catalog()['inserted'] == 0
    assert path.read_bytes() == original


def test_supported_api_contract_is_host_scoped_and_quota_reserved(archive, monkeypatch):
    import httpx
    from services.sales_intelligence import adapters
    grants = registry.grants()
    grants['muadzo'].update(adapter='canonical_json_v1', endpoint='https://muadzo.com/documented-fixture-api', endpoint_reference='Isolated documented contract fixture')
    (store.root() / 'access.json').write_text(json.dumps(grants))
    assert adapters.configuration('muadzo')['adapter'] == 'canonical_json_v1'
    monkeypatch.setattr(adapters, 'public_addresses', lambda host: None)
    original_client = httpx.Client
    captured = []
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json=[reading()])
    monkeypatch.setattr(adapters.httpx, 'Client', lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    assert adapters.fetch('muadzo', '123', 'fixture-reservation')['inserted'] == 1
    assert len(captured) == 1
    assert captured[0].url.params['listing_id'] == '123'
    with pytest.raises(ValueError, match='already reserved'):
        adapters.fetch('muadzo', '123', 'fixture-reservation')
    grants['muadzo']['endpoint'] = 'https://localhost/private'
    (store.root() / 'access.json').write_text(json.dumps(grants))
    with pytest.raises(ValueError, match='documented source host'):
        adapters.configuration('muadzo')


def test_student_frozen_splits_fit_activation_and_correction_staleness(archive, monkeypatch):
    import math
    at = store.now() - timedelta(days=300)
    samples = []
    for period in range(3):
        for shop in range(20):
            for listing in range(5):
                identity = str(1000 + shop * 5 + listing)
                x = (shop + listing) / 20
                start = at + timedelta(days=period * 40)
                samples.append({'id': f'{identity}-{period}', 'listing_id': identity, 'shop': f'fixture-shop-{shop}',
                    'start': start.isoformat(), 'end': (start + timedelta(days=30)).isoformat(), 'label': math.expm1(1 + x),
                    'teacher_sources': ['muadzo', 'hive'], 'feature': {'values': {'intercept': 1, 'favorites': x},
                    'metadata': {'category': 'fixture', 'product_type': 'digital'}}})
    frozen = {'id': 'fixture-dataset', 'samples': samples, 'policy_fingerprint': store.digest({s: registry.grants()[s] for s in ('muadzo', 'hive')}), 'correction_epoch': 0}
    monkeypatch.setattr(training, 'dataset', lambda days, unit: frozen)
    result = training.fit()
    assert result['qualified']
    assert result['actual_accuracy'] is None
    assert not set(result['train_ids']) & set(result['test_ids'])
    assert result['evaluation']['mae'] < result['evaluation']['baseline_mae']
    assert training.activate(result['id'])['lane'] == 'consensus_student'
    with store.database(True) as con:
        store.set_control(con, 'correction_epoch', 1)
    assert not training.eligible(result)
    with pytest.raises(ValueError, match='stale'):
        training.activate(result['id'])


def test_field_rates_use_each_measurements_time_and_stale_is_missing(archive):
    import math
    at = store.now() - timedelta(minutes=1)
    with store.database(True) as con:
        for days, value in [(10, 10), (2, 18), (0, None)]:
            date = (at - timedelta(days=days)).isoformat()
            store.add_metadata(con, {'listing_id': '123', 'shop_id': '789', 'captured_at': date,
                'available_at': date, 'favorites': value, 'views': 100 if days == 10 else None})
        result = features.snapshot(con, '123', at.isoformat())
    assert result['values']['favorites_rate'] == pytest.approx(math.log1p(1) / 10)
    assert result['metadata']['views'] is None
    assert result['values']['views_missing'] == 1


def test_name_only_metadata_cannot_enter_shop_held_out_dataset(archive):
    value = aligned(['muadzo', 'hive'], [20, 22])
    with store.database(True) as con:
        store.add_metadata(con, {'listing_id': '123', 'shop': 'Name is not an identity',
            'captured_at': value['period_end'], 'available_at': value['period_end']})
    assert training.dataset()['samples'] == []
    with store.database(True) as con:
        store.add_metadata(con, {'listing_id': '123', 'shop': 'Name is not an identity', 'shop_id': '789',
            'captured_at': value['period_end'], 'available_at': value['period_end']})
    assert training.dataset()['samples'][0]['shop'] == '789'


def test_quota_groups_month_one_time_and_dst(archive):
    grants = registry.grants()
    for source in ('etsimator', 'sellfinch'):
        grants[source]['quota'] = {'period': 'monthly', 'limit': 2, 'timezone': 'America/New_York'}
    (store.root() / 'access.json').write_text(json.dumps(grants))
    at = datetime(2026, 10, 31, 23, tzinfo=UTC)
    with store.database(True) as con:
        quotas.reserve(con, 'etsimator', 'shared-one', at=at)
        assert quotas.state(con, 'sellfinch', at)['remaining'] == 1
        assert quotas.state(con, 'sellfinch', at)['next_reset'] == '2026-11-01T04:00:00+00:00'
    grants['muadzo']['quota'] = {'period': 'one_time', 'limit': 1, 'timezone': 'UTC'}
    (store.root() / 'access.json').write_text(json.dumps(grants))
    with store.database(True) as con:
        quotas.reserve(con, 'muadzo', 'one-time')
        assert quotas.state(con, 'muadzo', store.now() + timedelta(days=50))['remaining'] == 0
    grants['hive']['quota'] = {'period': 'daily', 'limit': 2, 'timezone': 'America/New_York'}
    (store.root() / 'access.json').write_text(json.dumps(grants))
    with store.database() as con:
        # New York's November 1 day is 25 hours long.
        state = quotas.state(con, 'hive', datetime(2026, 11, 1, 4, tzinfo=UTC))
        assert state['next_reset'] == '2026-11-02T05:00:00+00:00'


def test_provider_429_cooldown_and_failed_charge_survive_restart(archive, monkeypatch):
    from services.sales_intelligence import adapters
    import httpx
    grants = registry.grants()
    grants['muadzo'].update(adapter='canonical_json_v1', endpoint='https://muadzo.com/fixture-export', endpoint_reference='Synthetic fixture contract')
    (store.root() / 'access.json').write_text(json.dumps(grants))
    monkeypatch.setattr(adapters, 'public_addresses', lambda host: None)
    original = httpx.Client
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(429, headers={'Retry-After': '7200'})
    monkeypatch.setattr(adapters.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(transport), **kwargs))
    with pytest.raises(httpx.HTTPStatusError):
        adapters.fetch('muadzo', '123', 'first-reservation')
    health = registry.source('muadzo')['health']
    assert health['status'] == 'rate_limited'
    assert store.stamp(health['retry_at']) > store.now() + timedelta(hours=1)
    with pytest.raises(ValueError, match='cooldown'):
        adapters.fetch('muadzo', '123', 'second-reservation')
    assert len(calls) == 1
    with store.database() as con:
        assert quotas.state(con, 'muadzo')['remaining'] == 1
        assert con.execute('SELECT status FROM quota_events').fetchone()[0] == 'failed_or_charge_unknown'


def test_outbox_replay_preserves_authored_research_and_never_calibrates_provider_values(archive):
    from services import selling_products as selling
    item = selling.save_opportunity({'name': 'Fixture planners', 'keyword': 'teacher planner', 'family': 'planner'})
    imported = selling.import_packet(item['id'], {'expected_fingerprint': item['fingerprint'], 'packet': {'listings': [
        {'listing_id': '123', 'title': 'Fixture planner', 'shop': 'Fixture', 'tags': ['teacher planner'], 'source_ref': 'Fixture saved listing'}]}})['opportunity']
    end = (store.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    aligned(['muadzo', 'hive'], [20, 24], period_end=end.isoformat(), period_start=(end - timedelta(days=30)).isoformat())
    job = service.queue_promotion('123', item['id'])
    assert service.flush_outbox()['delivered'] == 1
    after = selling.detail(item['id'])
    assert len(after['evidence']['observations']) == 2
    assert after['evidence']['calibration'] == []
    assert after['evidence']['listings'] == imported['evidence']['listings']
    assert service.queue_promotion('123', item['id'])['id'] == job['id']
    assert service.flush_outbox()['delivered'] == 0
    assert selling.detail(item['id'])['revision_count'] == after['revision_count']


def test_actual_model_fits_only_separate_outcomes_and_has_its_own_activation(archive):
    at = store.now() - timedelta(days=300)
    values = []
    with store.database(True) as con:
        for period in range(3):
            start = at + timedelta(days=40 * period)
            end = start + timedelta(days=30)
            for shop in range(25):
                for listing in range(10):
                    identity = str(10000 + shop * 10 + listing)
                    value = 10 if listing % 2 else 0
                    store.add_metadata(con, {'listing_id': identity, 'shop_id': str(100 + shop),
                        'captured_at': end.isoformat(), 'available_at': end.isoformat(), 'category': 'fixture',
                        'product_type': 'digital', 'favorites': 100000 if value else 0})
                    values.append({'listing_id': identity, 'shop': 'Fixture name', 'shop_id': str(100 + shop),
                        'period_start': start.isoformat(), 'period_end': end.isoformat(), 'available_at': end.isoformat(),
                        'actual': value, 'unit': 'purchases', 'source_ref': 'Synthetic seller totals',
                        'attestation': 'Isolated synthetic aggregate records, not real sales'})
    data = {'content': json.dumps(values)}
    check = ingestion.import_outcomes(data)
    ingestion.import_outcomes({**data, 'expected_fingerprint': check['fingerprint']})
    assert store.counts()['observations'] == 0
    result = training.fit(objective='actual')
    assert result['lane'] == 'actual_outcome'
    assert result['evaluation']['objective'] == 'actual_sales_accuracy_on_retained_outcomes'
    assert result['qualified'], result['evaluation']
    assert result['evaluation']['guardrails']['zero_cases'] >= 10
    assert training.activate(result['id'])['lane'] == 'actual_outcome'
    with store.database() as con:
        assert store.get_control(con, 'active:30:purchases') is None
        assert store.get_control(con, 'active:outcome:30:purchases') == result['id']
    assert training.prediction('10000')['status'] == 'no_active_model'
    assert training.prediction('10000', lane='actual_outcome')['status'] == 'metadata_stale'


def test_provider_source_mismatch_and_repeat_correction_do_not_change_lineage(archive):
    with pytest.raises(ValueError):
        save([reading(source='hive')])
    original = reading()
    save([original])
    with store.database() as con:
        identity = con.execute('SELECT id FROM observations').fetchone()[0]
    correction = {**original, 'value': 24, 'available_at': (store.now() - timedelta(seconds=10)).isoformat(), 'supersedes': identity}
    save([correction])
    with store.database() as con:
        epoch = store.get_control(con, 'correction_epoch')
    save([correction])
    with store.database() as con:
        assert store.get_control(con, 'correction_epoch') == epoch


def test_concurrent_first_migration_and_newer_runtime_guard(archive, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setenv('SALES_INTELLIGENCE_ROOT', str(archive / 'fresh-concurrent'))
    with ThreadPoolExecutor(max_workers=6) as pool:
        counts = list(pool.map(lambda _: store.counts(), range(12)))
    assert all(row['metadata'] == 0 for row in counts)
    with store.database(True) as con:
        con.execute('PRAGMA user_version=999')
    with pytest.raises(ValueError, match='newer runtime'):
        store.counts()
    with sqlite3.connect(store.root() / 'intelligence.sqlite') as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 999


def test_health_probe_does_not_migrate_or_scan_research(archive, monkeypatch):
    from pipeline import keyword_database as kdb
    from main import api_health
    path = archive / 'health.sqlite'
    monkeypatch.setattr(kdb, 'DB_PATH', path)
    assert not kdb.has_seeds() and not path.exists()
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE seeds(keyword TEXT)')
        con.execute("INSERT INTO seeds VALUES('fixture')")
    def forbidden():
        raise AssertionError('Health must not initialize or run research analytics')
    monkeypatch.setattr(kdb, 'init_db', forbidden)
    monkeypatch.setattr(kdb, 'get_stats', forbidden)
    assert api_health()['database'] == 'connected'


def test_unknown_model_read_does_not_wait_for_archive_writer(archive):
    from concurrent.futures import ThreadPoolExecutor
    with store.database(True), ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(training.prediction, '123').result(timeout=2)
    assert result == {'status': 'no_active_model', 'value': None}


def test_coverage_indexes_migrate_existing_archive_and_track_latest_metadata(archive):
    at = store.now() - timedelta(days=1)
    with store.database(True) as con:
        for identity, product, shop in [('123', 'digital', '7'), ('124', 'physical', '7'), ('125', 'unknown', None)]:
            store.add_metadata(con, {'listing_id': identity, 'product_type': product, 'shop_id': shop,
                'captured_at': at.isoformat(), 'available_at': at.isoformat()})
        before = con.execute('SELECT id,payload FROM metadata ORDER BY id').fetchall()
        for index in ('metadata_count', 'metadata_latest_type_shop', 'metadata_latest_shop'):
            con.execute('DROP INDEX ' + index)
        con.execute('PRAGMA user_version=3')
    report = service.coverage()
    assert report['metadata'] == 3 and report['listings'] == 3 and report['canonical_shops'] == 1
    assert {r['product_type']: (r['listings'], r['canonical_shops_known']) for r in report['catalog_types']} == {
        'digital': (1, 1), 'physical': (1, 1), 'unknown': (1, 0)}
    with store.database(True) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == store.SCHEMA
        assert con.execute('SELECT id,payload FROM metadata ORDER BY id').fetchall() == before
        queries = [
            "SELECT count(*) FROM metadata INDEXED BY metadata_count",
            "SELECT count(DISTINCT json_extract(payload,'$.shop_id')) FROM metadata_latest INDEXED BY metadata_latest_shop",
            "SELECT coalesce(json_extract(payload,'$.product_type'),'unknown') product_type,count(*),sum(json_extract(payload,'$.shop_id') IS NOT NULL) FROM metadata_latest INDEXED BY metadata_latest_type_shop GROUP BY product_type",
        ]
        for query in queries:
            plan = ' '.join(row[3] for row in con.execute('EXPLAIN QUERY PLAN ' + query))
            assert 'USING' in plan and 'INDEX' in plan and 'USE TEMP B-TREE' not in plan
        later = (at + timedelta(hours=1)).isoformat()
        store.add_metadata(con, {'listing_id': '123', 'product_type': 'physical', 'shop_id': '8',
            'captured_at': later, 'available_at': later})
    report = service.coverage()
    assert report['metadata'] == 4 and report['listings'] == 3 and report['canonical_shops'] == 2
    assert {r['product_type']: r['listings'] for r in report['catalog_types']} == {'physical': 2, 'unknown': 1}
