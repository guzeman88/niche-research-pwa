"""Isolated real collector -> existing estimator -> API tests, with no network."""
from contextlib import closing
from datetime import timedelta
import json
import pytest
from fastapi.testclient import TestClient
from models.selling_products import Listing, Packet
from services import selling_discovery as discovery, selling_discovery_sources as sources
from services.sales_intelligence import estimator, store, worker


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('VALIDATION_DB_PATH', str(tmp_path / 'ledger.sqlite'))
    monkeypatch.setenv('SALES_INTELLIGENCE_ROOT', str(tmp_path / 'archive'))
    monkeypatch.setenv('APP_KEYWORD_FEED_ROOT', str(tmp_path / 'native'))
    packet = Packet(listings=[Listing(listing_id='123', title='Isolated planner', shop='Shop A', source_ref='Fixture')]).model_dump(mode='json')
    with closing(discovery.connect()) as target, target:
        discovery._upsert(target, packet, 'teacher planner', store.now().isoformat())
    return tmp_path


def capture(monkeypatch, *, times=None, complete=True, count=None, malformed=False, identity='123'):
    at = store.now() - timedelta(seconds=1)
    times = times if times is not None else [at - timedelta(days=20), at - timedelta(days=2)]
    monkeypatch.setattr(discovery, 'now', lambda: at)
    class Client:
        scopes = {'listing_api', 'shop_api', 'listing_reviews'}
        def get(self, path, scope, params=None):
            if path.endswith('/reviews'):
                assert params['limit'] == 100 and params['max_created'] == int(at.timestamp())
                rows = [{'listing_id': 123 if not malformed else 999, 'created_timestamp': int(t.timestamp()),
                    'rating': 5, 'review': '', 'buyer_user_id': 'private-fixture'} for t in times]
                return {'results': rows, **({'count': len(rows) if count is None else count} if complete else {})}
            if path.endswith('/images'):
                return {'results': []}
            if scope == 'shop_api':
                return {'shop_name': 'Shop A', 'transaction_sold_count': 6000, 'review_count': 1000}
            return {'listing_id': int(identity), 'title': 'Isolated planner', 'shop_id': 7, 'listing_type': 'download', 'views': 500,
                    'quantity': 99, 'num_favorers': 70, 'price': {'amount': 800, 'divisor': 100, 'currency_code': 'USD'}}
    with closing(discovery.connect()) as target:
        row = target.execute('SELECT * FROM candidates WHERE listing_id=?', (identity,)).fetchone()
    packet, _ = sources.collect(Client(), row, retain_estimator=True)
    return at, packet


def test_collector_automatically_runs_original_estimator_without_teacher_or_outcomes(isolated, monkeypatch):
    at, packet = capture(monkeypatch)
    result = estimator.calculate('123')
    assert result['engine'] == 'etgen-sales-v1'
    assert result['status'] == 'uncalibrated_review_scenario'
    assert result['value'] == 20
    assert result['review_scenarios']['7']['value'] == 10
    assert result['review_scenarios']['30']['low'] == 6.67
    assert result['review_scenarios']['30']['high'] == 100
    assert result['accuracy'] == 'unvalidated' and result['training_required'] is False
    assert result['windows']['30']['estimate'] is None  # no fabricated measured conversion
    assert not any(o['metric'] == 'shop_reviews' for o in packet['observations'])
    assert packet['listings'][0]['product_type'] == 'digital'
    with store.database() as con:
        assert not any('private-fixture' in r[0] for r in con.execute('SELECT payload FROM estimator_evidence'))
    assert store.counts()['observations'] == store.counts()['outcomes'] == store.counts()['models'] == 0
    assert estimator.calculate('123', (at - timedelta(seconds=1)).isoformat())['value'] is None
    estimator.refresh()
    assert estimator.overview()['summary']['estimated'] == 1


@pytest.mark.parametrize('kwargs', [{'times': []}, {'complete': False}, {'count': 200}, {'malformed': True}])
def test_zero_missing_truncated_and_wrong_identity_do_not_become_sales(isolated, monkeypatch, kwargs):
    capture(monkeypatch, **kwargs)
    result = estimator.calculate('123')
    assert result['value'] is None
    assert result['status'] == 'needs_conversion_evidence'


def test_stale_and_future_cutoffs(isolated, monkeypatch):
    at, _ = capture(monkeypatch)
    with pytest.raises(ValueError, match='future'):
        estimator.calculate('123', (store.now() + timedelta(days=1)).isoformat())
    monkeypatch.setattr(store, 'now', lambda: at + timedelta(days=8))
    assert estimator.calculate('123')['status'] == 'stale_evidence'
    estimator.refresh()
    assert estimator.overview()['summary']['estimated'] == 0


def test_capture_idempotence_and_asof_no_future_evidence(isolated, monkeypatch):
    at, _ = capture(monkeypatch)
    with store.database() as con:
        before = con.execute('SELECT count(*) FROM estimator_evidence').fetchone()[0]
    # Same exact normalized public capture remains one record.
    monkeypatch.setattr(store, 'now', lambda: at + timedelta(seconds=1))
    monkeypatch.setattr(discovery, 'now', lambda: at)
    with store.database() as con:
        raw = json.loads(con.execute('SELECT payload FROM estimator_evidence').fetchone()[0])
    packet = {'listings': [raw['listing']], 'observations': raw['observations']}
    estimator.record_capture(packet, at, raw['review_window'])
    with store.database() as con:
        assert con.execute('SELECT count(*) FROM estimator_evidence').fetchone()[0] == before


def test_panel_stable_diverse_bounded_and_revisits_oldest_due_product(isolated):
    at = store.now()
    with closing(discovery.connect()) as target, target:
        for i in range(200, 280):
            p = Packet(listings=[Listing(listing_id=str(i), title=f'Planner {i}', shop=f'Shop {i // 3}', source_ref='Fixture')]).model_dump(mode='json')
            discovery._upsert(target, p, 'planner template', at.isoformat())
        first = estimator.ensure_panel(target)
        assert len(first) == 30 and first == estimator.ensure_panel(target)
        due = estimator.due_rows(target, at.isoformat())
        assert len(due) == 3
        ids = [r['listing_id'] for r in due]
        target.executemany('UPDATE candidates SET next_check=? WHERE listing_id=?', [((at + timedelta(hours=6)).isoformat(), i) for i in ids])
        assert not set(ids) & {r['listing_id'] for r in estimator.due_rows(target, at.isoformat())}
        target.execute("UPDATE candidates SET opportunity_id='authored' WHERE listing_id='279'")
        assert estimator.due_rows(target, at.isoformat())[0]['listing_id'] == '279'


def test_pause_blocks_automatic_estimation_jobs(isolated):
    with store.database(True) as con:
        store.set_control(con, 'paused', True)
    assert worker.cycle()['status'] == 'paused'
    with store.database() as con:
        assert con.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
    with closing(discovery.connect()) as target:
        assert estimator.due_rows(target, store.now().isoformat()) == []


def test_empty_listing_response_uses_documented_shop_reviews_without_misattribution(isolated, monkeypatch):
    at = store.now() - timedelta(seconds=1)
    monkeypatch.setattr(discovery, 'now', lambda: at)
    calls = []
    class Client:
        scopes = {'listing_api', 'shop_api', 'listing_reviews'}
        def get(self, path, scope, params=None):
            calls.append(path)
            if path == '/listings/123/reviews':
                return {'count': 0, 'results': []}
            if path == '/shops/7/reviews':
                return {'count': 2, 'results': [
                    {'listing_id': identity, 'shop_id': 7, 'create_timestamp': int((at-timedelta(days=2)).timestamp()), 'review': '', 'rating': 5}
                    for identity in (123, 456)]}
            if path.endswith('/images'):
                return {'results': []}
            if scope == 'shop_api':
                return {'shop_name': 'Shop A', 'transaction_sold_count': 100}
            return {'listing_id': 123, 'shop_id': 7, 'title': 'Isolated planner'}
    with closing(discovery.connect()) as target:
        row = target.execute("SELECT * FROM candidates WHERE listing_id='123'").fetchone()
    sources.collect(Client(), row, retain_estimator=True)
    result = estimator.calculate('123')
    assert len(calls) == 5 and '/shops/7/reviews' in calls
    assert result['value'] == 10
    assert result['review_evidence']['observed_reviews'] == 1
    assert result['review_evidence']['response_scope'] == 'shop_reviews_matched_by_listing_id'


def test_complete_shop_reviews_feed_known_related_products_without_extra_requests(isolated, monkeypatch):
    at=store.now()-timedelta(seconds=1)
    monkeypatch.setattr(discovery,'now',lambda:at)
    related=Packet(listings=[Listing(listing_id='456',title='Known related planner',shop='Shop A',source_ref='Fixture')]).model_dump(mode='json')
    with closing(discovery.connect()) as target,target:
        discovery._upsert(target,related,'teacher planner',at.isoformat())
    rows=[{'listing_id':456,'shop_id':7,'created_timestamp':int((at-timedelta(days=2)).timestamp()),'rating':5,'review':'Private fixture body','buyer_user_id':'must-not-retain'}]
    assert estimator.follow_reviewed_products(rows,at-timedelta(days=30),at,'7','123',{'shop':'Shop A'})==['456']
    value=estimator.calculate('456')
    assert value['value']==10 and value['listing']['title']=='Known related planner'
    assert estimator.calculate('123')['value'] is None
    with store.database() as con:
        assert 'must-not-retain' not in con.execute('SELECT payload FROM estimator_evidence').fetchone()[0]
        assert 'Private fixture body' not in con.execute('SELECT payload FROM estimator_evidence').fetchone()[0]
    with closing(discovery.connect()) as target:
        assert estimator.due_rows(target,at.isoformat())[0]['listing_id']=='456'
    assert estimator.follow_reviewed_products([{**rows[0],'listing_id':999}],at-timedelta(days=30),at,'7','123',{'shop':'Shop A'})==['999']
    unknown=estimator.calculate('999')
    assert unknown['value']==10 and unknown['listing']['title']==''
    with closing(discovery.connect()) as target:
        assert not target.execute("SELECT 1 FROM candidates WHERE listing_id='999'").fetchone()
        pending=next(r for r in estimator.due_rows(target,at.isoformat()) if r['listing_id']=='999')
        assert pending['pending_metadata'] and pending['keyword']==''
        estimator.record_check('999','source_unavailable',(at+timedelta(hours=24)).isoformat())
        assert '999' not in [r['listing_id'] for r in estimator.due_rows(target,at.isoformat())]
    assert estimator.follow_reviewed_products([rows[0],rows[0]],at-timedelta(days=30),at,'7','123',{'shop':'Shop A'})==[]


def test_duplicate_review_rows_and_full_page_never_claim_complete(isolated, monkeypatch):
    at = store.now() - timedelta(days=2)
    capture(monkeypatch, times=[at, at])
    assert estimator.calculate('123')['value'] is None
    capture(monkeypatch, times=[at - timedelta(minutes=i) for i in range(100)])
    assert estimator.calculate('123')['value'] is None


def test_private_routes_track_and_recalculation(isolated, monkeypatch):
    from main import app
    monkeypatch.setenv('PIPELINE_API_TOKEN', 'fixture-token')
    client = TestClient(app)
    assert client.get('/api/sales-intelligence/estimates').status_code == 401
    auth = {'Authorization': 'Bearer fixture-token'}
    assert client.post('/api/sales-intelligence/listings/123/track', headers=auth, json={}).status_code == 200
    assert client.post('/api/sales-intelligence/listings/999/track', headers=auth, json={}).status_code == 400
    assert client.post('/api/sales-intelligence/estimates/refresh', headers=auth, json={}).status_code == 202
    result = client.get('/api/sales-intelligence/estimates', headers=auth)
    assert result.status_code == 200 and 'no-store' in result.headers['cache-control']
    assert result.json()['items'][0]['value'] is None
