"""Research semantics, atomic preservation and private access; provider-free."""
import json
from datetime import datetime, timezone, timedelta
import sqlite3
import pytest
from fastapi.testclient import TestClient
from services import selling_products as service, product_validation as ledger


@pytest.fixture
def opportunity(tmp_path, monkeypatch):
    monkeypatch.setenv('VALIDATION_DB_PATH', str(tmp_path / 'private.sqlite'))
    monkeypatch.setenv('APP_KEYWORD_FEED_ROOT', str(tmp_path / 'absent-feed'))
    return service.save_opportunity({'name': 'Teacher planners', 'keyword': 'teacher planner', 'family': 'planner'})


def listing(identity='one', shop='Shop A'):
    return {'listing_id': identity, 'title': 'Weekly Teacher Planner', 'shop': shop,
            'tags': ['teacher planner', 'weekly planning'], 'source_ref': 'Operator saved listing'}


def observation(metric='estimated_sales', value=20, days=0, **extra):
    at = datetime.now(timezone.utc) - timedelta(days=days)
    return {'listing_id': 'one', 'metric': metric, 'value': value, 'observed_at': at.isoformat(),
            'basis': 'period', 'period_start': (at.date() - timedelta(days=6)).isoformat(),
            'period_end': at.date().isoformat(), 'source': 'everbee', 'source_ref': 'Saved provider report', **extra}


def load(item, **packet):
    result = service.import_packet(item['id'], {'packet': packet, 'expected_fingerprint': item['fingerprint']})
    return result['opportunity']


def brief(item):
    return service.save_brief(item['id'], {'expected_fingerprint': item['fingerprint'], 'brief': {
        'name': 'Original teacher planning pages', 'buyer': 'Teachers',
        'purpose': 'Help teachers organize their week with usable writing space.',
        'improvements': ['Larger writing areas', 'Worked example'],
        'original_direction': 'Create an independently authored clear grid and original instructions.', 'family': 'planner'}})


def test_empty_is_unknown_and_all_five_methods_exist(opportunity):
    assert opportunity['analysis']['evidence_level'] == 'needs_evidence'
    assert len(opportunity['analysis']['methods']) == 5
    assert all(row['status'] == 'needs_evidence' for row in opportunity['analysis']['methods'].values())


def test_atomic_import_idempotence_and_revision_preservation(opportunity):
    item = load(opportunity, listings=[listing()], observations=[observation()])
    count = item['record_count']
    again = load(item, listings=[listing()], observations=[observation(**{'observed_at': item['evidence']['observations'][0]['observed_at']})])
    assert again['record_count'] == count
    assert again['revision_count'] == item['revision_count']
    changed = dict(item['evidence']['observations'][0], value=25)
    corrected = load(again, observations=[changed])
    assert corrected['record_count'] == count
    assert corrected['revision_count'] == item['revision_count'] + 1
    with pytest.raises(ValueError):
        load(corrected, listings=[listing('two')], reviews=[{'review_id': 'bad', 'listing_id': 'absent',
            'reviewed_on': datetime.now(timezone.utc).date().isoformat(), 'rating': 2,
            'text': 'Tiny text', 'source_ref': 'Saved review'}])
    assert service.detail(item['id'])['record_count'] == count


def test_preview_does_not_write_and_stale_preview_cannot_overwrite(opportunity):
    preview = service.preview(opportunity['id'], {'format': 'json', 'content': json.dumps({'listings': [listing()]})})
    assert preview['added'] == 1
    assert service.detail(opportunity['id'])['fingerprint'] == opportunity['fingerprint']
    load(opportunity, listings=[listing('two')])
    with pytest.raises(service.Conflict):
        service.import_packet(opportunity['id'], {'packet': preview['packet'], 'expected_fingerprint': preview['fingerprint']})


def test_interest_shop_totals_and_lifetime_averages_are_not_recent_sales(opportunity):
    values = [observation('favorites', 500, basis='lifetime', period_start=None, period_end=None),
              observation('shop_sales', 5000, basis='lifetime', period_start=None, period_end=None),
              observation(basis='lifetime_average', period_start=None, period_end=None)]
    item = load(opportunity, listings=[listing()], observations=values)
    assert item['analysis']['recent_sales_listing_count'] == 0
    assert item['analysis']['methods']['bestsellers']['recent'] == []
    assert len(item['analysis']['methods']['bestsellers']['historical']) == 1
    assert any(r['scope'] == 'shop' for r in item['analysis']['methods']['momentum']['series']) is False


def test_stale_broad_period_and_missing_newer_values_are_not_current(opportunity):
    item = load(opportunity, listings=[listing()], observations=[observation(days=40)])
    assert item['analysis']['evidence_level'] == 'historical_estimates'
    item = load(item, observations=[observation(period_start=(datetime.now(timezone.utc).date() - timedelta(days=365)).isoformat())])
    assert item['analysis']['recent_sales_listing_count'] == 0
    item = load(item, observations=[observation(days=1), observation(value=None)])
    assert item['analysis']['recent_sales_listing_count'] == 0


def test_provider_estimates_are_not_added_and_conflicting_values_are_visible(opportunity):
    at = observation()
    item = load(opportunity, listings=[listing()], observations=[at, {**at, 'source': 'alura', 'value': 100}])
    assert item['analysis']['recent_sales_listing_count'] == 1
    assert len(item['analysis']['methods']['bestsellers']['recent']) == 2
    item = load(item, observations=[{**at, 'source_ref': 'Contradictory same-time report', 'value': 999}])
    assert len(item['analysis']['conflicts']) == 1
    assert len(item['analysis']['methods']['bestsellers']['recent']) == 1


def test_comparable_momentum_and_counter_decrease(opportunity):
    counters = [observation('reviews', value, days=days, basis='lifetime', period_start=None, period_end=None)
                for value, days in [(10, 8), (14, 1)]]
    item = load(opportunity, listings=[listing()], observations=[*counters, observation(days=8), observation(value=30, days=1)])
    series = item['analysis']['methods']['momentum']['series']
    assert {row['metric']: row['change'] for row in series} == {'reviews': 4, 'estimated_sales': 10}
    item = load(item, observations=[observation('reviews', 3, basis='lifetime', period_start=None, period_end=None)])
    row = next(r for r in item['analysis']['methods']['momentum']['series'] if r['metric'] == 'reviews')
    assert row['change'] is None and row['status'] == 'counter_decreased'


def test_review_mining_keyword_attribution_and_manual_patterns(opportunity):
    day = datetime.now(timezone.utc).date().isoformat()
    item = load(opportunity, listings=[listing(), listing('two', 'Shop B')], reviews=[
        {'review_id': 'a', 'listing_id': 'one', 'reviewed_on': day, 'rating': 2, 'text': 'The font is tiny and hard to read.', 'source_ref': 'Review A'},
        {'review_id': 'b', 'listing_id': 'two', 'reviewed_on': day, 'rating': 3, 'text': 'I wish the text was larger and readable.', 'source_ref': 'Review B'}],
        patterns=[{'listing_id': 'one', 'layout': 'structured', 'features': ['letter', 'instructions'], 'readability': 2, 'source_ref': 'Operator inspection'}])
    assert item['analysis']['evidence_level'] == 'recent_reviews'
    assert item['analysis']['methods']['reviews']['themes']['readability']['repeated']
    terms = item['analysis']['methods']['keywords']['terms']
    assert next(r for r in terms if r['keyword'] == 'teacher planner')['shops'] == 2
    assert all(r['sales_attribution'] == 'unknown' for r in terms)
    assert item['analysis']['methods']['patterns']['features']['letter'] == 1
    assert item['analysis']['methods']['patterns']['missing_traits_are_unknown']


def test_brief_intake_is_original_incomplete_and_invalidates_on_evidence_change(opportunity):
    item = load(opportunity, listings=[listing()])
    item = brief(item)
    spec = service.production_intake(item['id'])
    assert spec['content'] == [] and spec['price'] is None and spec['tags'] == []
    assert spec['artwork_id'] is None and not spec['research']['qualification_credit']
    item = load(item, observations=[observation()])
    assert item['brief']['stale']
    with pytest.raises(service.Conflict):
        service.production_intake(item['id'])


def test_export_checksum_round_trip_and_validation_link_does_not_invent_evidence(opportunity):
    item = load(opportunity, listings=[listing()], observations=[observation()])
    exported = service.export(item['id'])
    packet = service.parse_import({'format': 'json', 'content': json.dumps(exported)})
    assert len(packet['listings']) == 1 and exported['can_publish'] is False
    exported['evidence']['listings'][0]['title'] = 'Tampered title'
    with pytest.raises(ValueError, match='checksum'):
        service.parse_import({'format': 'json', 'content': json.dumps(exported)})
    link = service.link_validation(item['id'])
    assert service.link_validation(item['id']) == link
    assert len(ledger.records(link['project_id'])) == 1


def test_csv_aliases_bounds_and_unknown_metrics(opportunity):
    packet = service.parse_import({'format': 'csv', 'dataset': 'listings',
        'content': 'Product ID,Title,Shop Name,source_ref\n123,Teacher planner,Shop A,Manual inspection\n'})
    assert packet['listings'][0]['listing_id'] == '123'
    with pytest.raises(ValueError):
        service.preview(opportunity['id'], {'format': 'json', 'content': json.dumps({'observations': [observation(value=True)]})})
    with pytest.raises(ValueError):
        service.preview(opportunity['id'], {'format': 'json', 'content': json.dumps({'listings': [listing()], 'observations': [observation(basis='point_in_time')]})})


def test_private_reads_and_mutations_require_authorization(opportunity, monkeypatch):
    monkeypatch.setenv('PIPELINE_API_TOKEN', 'fixture-only-token')
    from main import app
    client = TestClient(app)
    assert client.get('/api/selling-products').status_code == 401
    assert client.get('/api/selling-products/opportunities/' + opportunity['id']).status_code == 401
    response = client.get('/api/selling-products/opportunities/' + opportunity['id'] + '/export', headers={'Authorization': 'Bearer fixture-only-token'})
    assert response.status_code == 200 and response.headers['cache-control'] == 'private, no-store'


def test_saved_research_is_read_only_and_does_not_create_sales(opportunity, tmp_path, monkeypatch):
    path = tmp_path / 'research.sqlite'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE keyword_listing_snapshots(keyword,title,listing_id,shop_name,url,observed_at,price,currency_code,review_count,favorites,collection_run_id)')
        con.execute('INSERT INTO keyword_listing_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            ('teacher planner', 'Teacher planner', '123', 'Shop A', '', datetime.now(timezone.utc).isoformat(), 5, 'USD', 10, 20, 'fixture'))
    from services import research_listing
    def connection():
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        return con
    monkeypatch.setattr(research_listing, 'research_connection', connection)
    before = path.read_bytes()
    result = service.research('teacher planner')
    assert result['external_requests'] == 0 and result['sales_available'] is False
    assert {r['metric'] for r in result['packet']['observations']} == {'price', 'reviews', 'favorites'}
    assert path.read_bytes() == before


def test_incomparable_reporting_windows_and_price_currencies(opportunity):
    item = load(opportunity, listings=[listing()], observations=[observation(days=9), observation(period_start=(datetime.now(timezone.utc).date()-timedelta(days=13)).isoformat()),
        observation('price', 10, days=5, basis='point_in_time', period_start=None, period_end=None, currency='USD'),
        observation('price', 11, basis='point_in_time', period_start=None, period_end=None, currency='CAD')])
    series = item['analysis']['methods']['momentum']['series']
    assert all(row['change'] is None and row['status'] == 'incomparable_windows' for row in series)


def test_malformed_scope_and_csv_alias_collision_are_rejected(opportunity):
    with pytest.raises(ValueError, match='overlap'):
        service.parse_import({'format': 'csv', 'content': 'Product ID,listing_id,title,source_ref\n1,2,Teacher planner,Report'})
    for row in [observation('seller_reported_sales'), observation(observed_at='2026-01-01T12:00:00'), observation(value=-1), observation(value=float('inf')),
                observation(period_end=(datetime.now(timezone.utc).date()+timedelta(days=1)).isoformat())]:
        with pytest.raises(ValueError):
            load(opportunity, listings=[listing()], observations=[row])
    assert service.detail(opportunity['id'])['record_count'] == 1


def test_production_rechecks_authoritative_brief_and_preserves_revision_origin(opportunity, monkeypatch):
    from services import production, research_listing
    item = brief(load(opportunity, listings=[listing()], observations=[observation()]))
    intake = service.production_intake(item['id'])
    captured = []
    class Engine:
        def submit(self, spec, product):
            captured.append(spec)
            return {'spec': spec}
    monkeypatch.setattr(production, 'engine', Engine)
    monkeypatch.setattr(production, 'mirror', lambda job: None)
    def unavailable(keyword):
        raise ValueError('No demand evidence')
    monkeypatch.setattr(research_listing, 'current_candidate', unavailable)
    first = production.submit({'spec': intake})
    origin = first['spec']['research']['selling_products']
    assert origin['selling_opportunity'] == item['id'] and origin['qualification_credit'] is False
    production.submit({'spec': first['spec']})
    assert captured[-1]['research']['selling_products'] == origin
    with pytest.raises(ValueError):
        production.submit({'spec': {'research': 'malformed'}})
    load(item, observations=[observation(value=30)])
    with pytest.raises(ValueError):
        production.submit({'spec': intake})
    assert len(captured) == 2
