"""Private pipeline integration, fresh evidence semantics and bounded access."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import gzip
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient
from models.selling_products import Listing, Observation, Packet, Review
from services import selling_discovery as feed, selling_products as selling
from services import selling_discovery_sources as source, selling_discovery_worker as worker
from services import feed_request_budget as budget, product_validation as ledger


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    monkeypatch.setenv('VALIDATION_DB_PATH', str(tmp_path / 'ledger.sqlite'))
    native = tmp_path / 'native'
    path = native / 'data/catalog.sqlite'
    path.parent.mkdir(parents=True)
    monkeypatch.setenv('APP_KEYWORD_FEED_ROOT', str(native))
    (native / 'installation.json').write_text(json.dumps({'database': str(path)}))
    with sqlite3.connect(path) as con:
        con.execute('''CREATE TABLE keyword_listing_snapshots(id INTEGER PRIMARY KEY,listing_id TEXT,
          title TEXT,keyword TEXT,shop_name TEXT,observed_at TEXT,price REAL,currency_code TEXT,
          favorites INTEGER,review_count INTEGER,collection_run_id TEXT)''')
        con.executemany('INSERT INTO keyword_listing_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)', [
            (i, str(100 + i), f'Fixture planner {i}', 'teacher planner', f'Shop {i}',
             feed.now().isoformat(), 10, 'USD', i, None, 'test-run') for i in range(1, 4)])
    return path


def packet(identity='101', hours=0, window=24, message=True, review=False):
    at = feed.now() - timedelta(hours=hours)
    observations = [Observation(listing_id=identity, metric='purchase_message', value=12,
        observed_at=at, source='etsy_public', source_ref='https://www.etsy.com/listing/' + identity,
        raw_message=f'12 people bought this in the past {window} hours', unit='buyers', window_hours=window)] if message else []
    reviews = [Review(listing_id=identity, review_id='review1', reviewed_on=at.date(), rating=2,
        text='The instructions need a worked example and larger type.', source_ref='Public listing review')] if review else []
    return Packet(listings=[Listing(listing_id=identity, title='Fixture planner', source_ref='Fixture listing')],
                  observations=observations, reviews=reviews).model_dump(mode='json')


def insert(value):
    with closing(feed.connect()) as con, con:
        feed._upsert(con, value, 'teacher planner', feed.now().isoformat())


def authorize(scopes):
    path = feed.root() / 'etsy-authorization.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'issuer': 'Etsy', 'reference': 'Isolated fixture approval only',
        'issued_at': (feed.now() - timedelta(days=1)).isoformat(),
        'expires_at': (feed.now() + timedelta(days=1)).isoformat(), 'scopes': scopes}))


def test_incremental_atomic_cursor_no_source_writes(catalog, monkeypatch):
    original = catalog.read_bytes()
    monkeypatch.setattr(feed, 'BATCH', 2)
    assert feed.sync_catalog()['scanned'] == 2
    assert feed.sync_catalog()['scanned'] == 1
    assert feed.sync_catalog()['scanned'] == 0
    data = feed.browse()
    assert data['counts'] == {'indexed': 3, 'purchase_reports': 0, 'review_activity': 0}
    assert all(v['signal'] == 'unknown' and v['favorites'] for v in data['items'])
    assert catalog.read_bytes() == original
    assert len(feed.browse('planner', page=1, limit=2)['items']) == 1
    assert not feed.browse('not a match')['items']
    assert not feed.browse(signal='purchase_report')['items']


def test_malformed_row_skipped_and_future_not_adopted(catalog):
    with sqlite3.connect(catalog) as con:
        con.execute("UPDATE keyword_listing_snapshots SET observed_at='2099-01-01T00:00:00+00:00' WHERE id=1")
        con.execute("UPDATE keyword_listing_snapshots SET listing_id='not-numeric' WHERE id=2")
    assert feed.sync_catalog()['skipped'] == 2
    assert feed.browse()['counts']['indexed'] == 1


def test_approval_never_inferred_and_expiry(catalog):
    assert feed.approval()['scopes'] == []
    authorize(['listing_pages'])
    assert feed.approval()['scopes'] == ['listing_pages']
    p = feed.root() / 'etsy-authorization.json'
    value = json.loads(p.read_text()); value['expires_at'] = (feed.now() - timedelta(seconds=1)).isoformat()
    p.write_text(json.dumps(value))
    assert feed.approval()['scopes'] == []


def test_purchase_expiry_units_reviews_and_no_rolling_sums(catalog):
    insert(packet(hours=2, window=1))
    assert feed.browse()['items'][0]['signal'] == 'unknown'
    insert(packet(hours=.1, window=1))
    assert feed.browse()['counts']['purchase_reports'] == 1
    assert feed.browse()['items'][0]['purchase_report']['value'] == 12
    insert(packet('102', hours=25))
    insert(packet('103', message=False, review=True))
    assert feed.browse()['counts'] == {'indexed': 3, 'purchase_reports': 1, 'review_activity': 1}
    assert feed.browse(signal='review_activity')['items'][0]['signal'] == 'review_activity'
    unknown = packet('104'); unknown['observations'][0].update(unit='unknown', raw_message='12 bought this in the past 24 hours')
    insert(unknown)
    assert feed.browse()['counts']['purchase_reports'] == 1


def test_investigate_idempotent_and_updates_stale_brief(catalog):
    feed.sync_catalog()
    candidate = feed.browse('planner 1')['items'][0]
    item = feed.investigate('101', candidate['fingerprint'])
    again = feed.investigate('101', candidate['fingerprint'])
    assert again['id'] == item['id']
    assert again['revision_count'] == item['revision_count']
    item = selling.save_brief(item['id'], {'expected_fingerprint': item['fingerprint'], 'brief': {
        'name': 'Original accessible planning pages', 'buyer': 'Teachers', 'purpose': 'Organize a teaching week with readable pages.',
        'improvements': ['Larger text', 'Worked example'], 'original_direction': 'Write independent content with an original page structure.', 'family': 'planner'}})
    insert(packet())
    feed.sync_watchlist()
    after = selling.detail(item['id'])
    assert after['brief']['stale']
    assert len(ledger.records(kind='selling_opportunity')) == 1
    assert after['analysis']['sales_model']
    with pytest.raises(selling.Conflict):
        feed.investigate('101', candidate['fingerprint'])


def test_empty_and_selected_watchlists_use_only_the_partial_index(catalog):
    feed.sync_catalog()
    assert feed.sync_watchlist() == 0
    with closing(feed.connect()) as con:
        plan = con.execute('EXPLAIN QUERY PLAN SELECT listing_id,packet,opportunity_id FROM candidates INDEXED BY candidates_watchlist WHERE opportunity_id IS NOT NULL').fetchall()
        assert any('candidates_watchlist' in row[3] for row in plan)
    candidate = feed.browse('planner 1')['items'][0]
    item = feed.investigate(candidate['listing_id'], candidate['fingerprint'])
    assert feed.sync_watchlist() == 1
    assert len(ledger.records(kind='selling_opportunity')) == 1
    assert selling.detail(item['id'])['fingerprint'] == item['fingerprint']


def test_scoped_html_parser_fails_unknown_for_recommendations():
    prefix = '<link rel="canonical" href="https://www.etsy.com/listing/101/planner">'
    assert source.purchase_message(prefix + '<aside>12 people bought this in the past 24 hours</aside>', '101') is None
    assert source.purchase_message(prefix + '<div id="listing-page-cart"><span>In 12 carts</span></div>', '101') is None
    assert source.purchase_message(prefix + '<div id="listing-page-cart"><script>12 people bought this in the past 24 hours</script></div>', '101') is None
    raw = prefix + '<div id="listing-page-cart"><p><span>12 people</span> bought this in the past 24 hours</p></div>'
    assert source.purchase_message(raw, '101')[1]['unit'] == 'buyers'
    assert source.purchase_message(raw, '999') is None
    assert source.purchase_message(raw.replace('</div>', '<p>15 people bought this in the past 24 hours</p></div>'), '101') is None


def test_source_no_authorization_no_requests_and_shared_reserve(catalog, monkeypatch):
    feed.sync_catalog()
    assert source.refresh_sources(1)['requests'] == 0
    authorize(['listing_pages'])
    with sqlite3.connect(catalog) as con:
        budget.schema(con)
        quota = {'limit_per_day': 1000, 'remaining_today': 100, 'captured_at': feed.now().isoformat()}
        con.execute('INSERT INTO feed_etsy_requests(batch_id,attempted_at,status,quota_json) VALUES(?,?,?,?)',
                    ('native', feed.now().isoformat(), '200', json.dumps(quota)))
    assert source.refresh_sources(2)['status'] == 'budget_deferred'
    with sqlite3.connect(catalog) as con:
        assert con.execute('SELECT count(*) FROM feed_etsy_requests').fetchone()[0] == 1


def test_http_denial_persisted_and_html_never_sends_key(catalog):
    authorize(['listing_pages'])
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(429, headers={'retry-after': '30'})
    with sqlite3.connect(catalog) as con:
        budget.schema(con)
        client = source.Client(con, 'fixture', ['listing_pages'], httpx.Client(transport=httpx.MockTransport(respond)))
        with pytest.raises(source.SourceUnavailable, match='rate_limited'):
            client.get('/listings/101', 'listing_pages')
        with pytest.raises(budget.CollectionDeferred):
            client.get('/listings/102', 'listing_pages')
        assert len(requests) == 1
        assert 'x-api-key' not in requests[0].headers
        assert budget.latest_quota(con)['retry_after_until'] > datetime.now().timestamp()


def test_supported_listing_response_reaches_history_without_another_request(catalog, monkeypatch):
    from services.sales_intelligence import features, store
    from adapters.research import etsy_open_api
    authorize(['listing_api'])
    monkeypatch.setattr(etsy_open_api, '_api_key_header', lambda: 'isolated-secret')
    calls = []
    payload = {'listing_id': 101, 'title': 'Saved API fixture', 'shop_id': 7,
        'price': {'amount': 800, 'divisor': 100, 'currency_code': 'USD', 'unknown_nested': 'must-not-retain'},
        'listing_type': 'download', 'views': 23, 'num_favorers': 5, 'quantity': 9,
        'buyer_user_id': 'must-not-retain', 'unrecognized_field': 'must-not-retain'}
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=payload)
    with sqlite3.connect(catalog) as con:
        budget.schema(con)
        client = source.Client(con, 'fixture-history', ['listing_api'], httpx.Client(transport=httpx.MockTransport(respond)))
        try:
            assert client.get('/listings/101', 'listing_api') == payload
        finally:
            client.close()
        archived = json.loads(gzip.decompress(con.execute('SELECT response_gzip FROM feed_etsy_requests').fetchone()[0]))
        assert archived['listing_id'] == 101 and archived['quantity'] == 9
        assert 'buyer_user_id' not in archived and 'unrecognized_field' not in archived
        assert 'unknown_nested' not in archived['price']
        assert 'isolated-secret' not in json.dumps(archived)
    original = catalog.read_bytes()
    assert features.sync_raw_catalog()['inserted'] == 1
    assert features.sync_raw_catalog()['inserted'] == 0
    assert catalog.read_bytes() == original
    assert len(calls) == 1
    with store.database() as con:
        value = json.loads(con.execute('SELECT payload FROM metadata_latest').fetchone()[0])
        assert value['views'] == 23 and value['stock'] == 9 and value['shop_id'] == '7'
        assert value['product_type'] == 'digital'
    assert store.counts()['observations'] == 0 and store.counts()['outcomes'] == 0


@pytest.mark.parametrize('scope,path,payload,status', [
    ('listing_reviews', '/listings/101/reviews', {'results': [{'buyer_user_id': 'private-fixture'}]}, 200),
    ('listing_api', '/listings/101/images', {'results': [{'url': 'fixture'}]}, 200),
    ('shop_api', '/shops/7', {'shop_id': 7}, 200),
    ('listing_api', '/listings/101', {'listing_id': 999, 'title': 'Wrong listing'}, 200),
    ('listing_api', '/listings/101', {'error': 'forbidden'}, 403),
    ('listing_api', '/listings/101', 'not JSON', 200),
])
def test_saved_response_excludes_other_sources_mismatch_errors_and_partial_data(catalog, monkeypatch, scope, path, payload, status):
    from adapters.research import etsy_open_api
    authorize([scope])
    monkeypatch.setattr(etsy_open_api, '_api_key_header', lambda: 'isolated-secret')
    response = httpx.Response(status, text=payload) if isinstance(payload, str) else httpx.Response(status, json=payload)
    with sqlite3.connect(catalog) as con:
        budget.schema(con)
        client = source.Client(con, 'fixture-exclusion', [scope], httpx.Client(transport=httpx.MockTransport(lambda request: response)))
        try:
            if status == 403 or isinstance(payload, str):
                with pytest.raises(ValueError):
                    client.get(path, scope)
            else:
                client.get(path, scope)
        finally:
            client.close()
        row = con.execute('SELECT status,response_gzip FROM feed_etsy_requests').fetchone()
        assert row[0] == str(status) and row[1] is None


def test_worker_restart_recovery_and_no_manual_sales(catalog):
    result = worker.cycle()
    assert result['scanned'] == 3 and result['requests'] == 0
    assert result['source_status'] == 'authorization_unverified'
    assert feed.browse()['counts']['purchase_reports'] == 0
    with closing(feed.connect()) as con, con:
        con.execute("INSERT INTO runs(started_at,status) VALUES(?,'running')", (feed.now().isoformat(),))
    worker.cycle()
    with closing(feed.connect()) as con:
        assert con.execute("SELECT count(*) FROM runs WHERE status='interrupted'").fetchone()[0] == 1


def test_busy_native_retries_locally_without_shortening_successful_request_cadence(catalog, monkeypatch):
    at = feed.now()
    calls = []
    def refresh(run_id):
        calls.append(run_id)
        return {'status': 'native_collector_running' if len(calls) == 1 else 'completed', 'requests': 0 if len(calls) == 1 else 1}
    monkeypatch.setattr(source, 'refresh_sources', refresh)
    worker.cycle()
    with closing(feed.connect()) as con:
        retry = feed._time(con.execute("SELECT value FROM control WHERE name='source_pass_after'").fetchone()[0])
    assert at < retry <= at + timedelta(seconds=70)
    monkeypatch.setattr(feed, 'now', lambda: at + timedelta(seconds=90))
    assert worker.cycle()['requests'] == 1
    assert worker.cycle()['requests'] == 0
    assert len(calls) == 2


def test_private_routes_and_conflict(catalog, monkeypatch):
    from main import app
    monkeypatch.setenv('PIPELINE_API_TOKEN', 'test-token')
    client = TestClient(app)
    assert client.get('/api/selling-products/discovery').status_code == 401
    auth = {'Authorization': 'Bearer test-token'}
    assert client.post('/api/selling-products/discovery/refresh', headers=auth, json={}).status_code == 202
    response = client.get('/api/selling-products/discovery', headers=auth)
    assert response.status_code == 200 and 'no-store' in response.headers['cache-control']
    assert response.json()['total'] == 3
    assert client.get('/api/selling-products/discovery?page=-1', headers=auth).status_code == 422
    assert client.post('/api/selling-products/discovery/101/investigate', headers=auth, json={'expected_fingerprint': 'old'}).status_code == 409


def test_image_urls_reject_external_and_credential_leaks():
    for url in ('https://example.com/a.png', 'http://i.etsystatic.com/a.png', 'https://secret@i.etsystatic.com/a.png'):
        with pytest.raises(ValueError):
            Listing(listing_id='101', title='A planner', source_ref='Fixture', image_url=url)


def test_documented_source_payloads_preserve_scope(catalog):
    feed.sync_catalog()
    with closing(feed.connect()) as con:
        row = con.execute("SELECT * FROM candidates WHERE listing_id='101'").fetchone()
    class FixtureClient:
        scopes = {'listing_api', 'shop_api', 'listing_reviews', 'listing_pages'}

        def get(self, path, scope, params=None):
            if scope == 'listing_pages':
                return '<link rel="canonical" href="https://www.etsy.com/listing/101/planner"><div id="listing-page-cart"><p>Over 12 people bought this in the past 24 hours</p></div>'
            if path.endswith('/images'):
                return {'results': [{'url_570xN': 'https://i.etsystatic.com/fixture.jpg'}]}
            if path.endswith('/reviews'):
                return {'results': [{'listing_id': 101, 'create_timestamp': int(feed.now().timestamp()), 'rating': 2,
                                     'review': 'Please improve the instructions.', 'buyer_user_id': 'do-not-store'}]}
            if scope == 'shop_api':
                return {'shop_name': 'Fixture shop', 'transaction_sold_count': 1000, 'review_count': 100}
            return {'listing_id': 101, 'title': 'Fixture planner updated', 'shop_id': 7, 'tags': ['teacher planner'],
                    'views': 100, 'num_favorers': 5, 'price': {'amount': 800, 'divisor': 100, 'currency_code': 'USD'}}
    value, status = source.collect(FixtureClient(), row)
    assert status == 'purchase_message_observed'
    assert value['listings'][0]['image_url'].startswith('https://i.etsystatic.com/')
    assert value['observations'][-1]['precision'] == 'lower_bound'
    assert value['observations'][-1]['unit'] == 'buyers'
    assert 'buyer_user_id' not in json.dumps(value)
    assert next(v for v in value['observations'] if v['metric'] == 'shop_sales')['value'] == 1000
    assert not any(v['metric'] == 'shop_reviews' for v in value['observations'])
    insert(value)
    candidate = feed.browse(signal='purchase_report')['items'][0]
    item = feed.investigate('101', candidate['fingerprint'])
    assert item['analysis']['sales_model']['listings'][0]['purchase_evidence'][0]['unit'] == 'buyers'
    # New sparse native observations retain enriched API metadata and images.
    feed.sync_catalog()
    sparse = Packet(listings=[Listing(listing_id='101', title='Sparse snapshot', source='saved_research', source_ref='New catalog snapshot')]).model_dump(mode='json')
    insert(sparse)
    assert feed.browse(signal='purchase_report')['items'][0]['image_url'] == 'https://i.etsystatic.com/fixture.jpg'


def test_conflicting_messages_do_not_get_purchase_badge(catalog):
    value = packet()
    other = dict(value['observations'][0], value=15, raw_message='15 people bought this in the past 24 hours', source_ref='Conflicting public capture')
    value['observations'].append(other)
    insert(value)
    assert feed.browse()['counts']['purchase_reports'] == 0
    assert feed.browse()['items'][0]['signal'] == 'unknown'
