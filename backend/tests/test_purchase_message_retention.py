"""Actual collector -> private archive -> estimator regressions; no network."""
from datetime import timedelta
import json

import pytest

from services import selling_discovery as discovery, selling_discovery_sources as sources, sales_model
from services.sales_intelligence import estimator, store


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setenv('VALIDATION_DB_PATH', str(tmp_path / 'ledger.sqlite'))
    monkeypatch.setenv('SALES_INTELLIGENCE_ROOT', str(tmp_path / 'archive'))
    monkeypatch.setenv('APP_KEYWORD_FEED_ROOT', str(tmp_path / 'native'))


def packet(observations=()):
    return {'listings': [{'listing_id': '123', 'title': 'Public fixture planner',
                         'shop': 'Fixture shop', 'source': 'etsy_public',
                         'source_ref': 'https://www.etsy.com/listing/123'}],
            'observations': list(observations)}


def message(at, raw='12 people bought this in the past 24 hours'):
    parsed = sales_model.parse_message(raw)
    return {**parsed, 'listing_id': '123', 'observed_at': at.isoformat(),
            'source': 'etsy_public', 'source_ref': 'https://www.etsy.com/listing/123'}


def collect(monkeypatch, raw, *, scopes=None, cached_review_end=None):
    at = store.now() - timedelta(seconds=1)
    monkeypatch.setattr(discovery, 'now', lambda: at)
    calls = []

    class Client:
        optimized = cached_review_end is not None

        def __init__(self):
            self.scopes = scopes if scopes is not None else {'listing_api', 'listing_pages'}

        def get(self, path, scope, params=None):
            calls.append((path, scope))
            if scope == 'listing_pages':
                return ('<link rel="canonical" href="https://www.etsy.com/listing/123/planner">'
                        '<aside>99 people bought this in the past 24 hours</aside>'
                        '<div id="listing-page-cart"><p>' + raw + '</p></div>')
            if path.endswith('/images'):
                return {'results': []}
            return {'listing_id': 123, 'shop_id': 7, 'title': 'Public fixture planner',
                    'quantity': 10, 'buyer_user_id': 'private-fixture-must-not-persist'}

    if cached_review_end:
        from services import selling_collection as cache
        monkeypatch.setattr(cache, 'reviews', lambda *args: {
            'start': int((cached_review_end - timedelta(days=30)).timestamp()),
            'end': int(cached_review_end.timestamp()), 'rows': [],
            'status': 'complete', 'reason': 'fixture cached complete window', 'pages': 1})
    value, status = sources.collect(Client(), {'listing_id': '123', 'packet': json.dumps(packet())}, True)
    return at, value, status, calls


@pytest.mark.parametrize('raw,unit,precision', [
    ('12 people bought this in the past 24 hours', 'buyers', 'exact'),
    ('Over 12 people bought this in the past 24 hours', 'buyers', 'lower_bound'),
    ('12 bought this in the past 24 hours', 'unknown', 'exact'),
])
def test_collector_message_survives_archive_and_calculation_without_conversion(archive, monkeypatch, raw, unit, precision):
    at, value, status, calls = collect(monkeypatch, raw)
    assert status == 'purchase_message_observed'
    assert len(calls) == 3 and calls[-1] == ('/listings/123', 'listing_pages')
    result = estimator.calculate('123')
    assert result['value'] is None and result['accuracy'] == 'unvalidated'
    assert result['windows']['30']['estimate'] is None
    observed = result['purchase_evidence'][0]
    assert (observed['value'], observed['unit'], observed['precision'], observed['window_hours']) == (12, unit, precision, 24)
    assert observed['raw_message'] == raw and store.stamp(observed['observed_at']) == at
    assert 'purchase_unit_or_bound_not_convertible' in result['issues']
    with store.database() as con:
        saved = con.execute('SELECT payload FROM estimator_evidence').fetchone()[0]
    assert 'private-fixture-must-not-persist' not in saved
    assert store.counts()['models'] == store.counts()['outcomes'] == 0


def test_retention_drops_private_fields_and_rejects_relabeling_as_purchases(archive):
    at = store.now() - timedelta(hours=1)
    row = {**message(at), 'buyer_email': 'private-fixture', 'note': 'private note fixture'}
    estimator.record_capture(packet([row]), at)
    with store.database() as con:
        before = con.execute('SELECT count(*) FROM estimator_evidence').fetchone()[0]
        saved = con.execute('SELECT payload FROM estimator_evidence').fetchone()[0]
    assert 'private-fixture' not in saved and 'private note fixture' not in saved
    with pytest.raises(ValueError):
        estimator.record_capture(packet([{**row, 'unit': 'purchases'}]), at)
    with store.database() as con:
        assert con.execute('SELECT count(*) FROM estimator_evidence').fetchone()[0] == before


def test_conflicting_public_messages_remain_unknown_after_persistence(archive):
    at = store.now() - timedelta(hours=1)
    estimator.record_capture(packet([message(at), message(at, '15 people bought this in the past 24 hours')]), at)
    result = estimator.calculate('123')
    assert result['value'] is None and result['purchase_evidence'] == []
    assert 'missing_or_conflicting_purchase_message' in result['issues']


def test_unavailable_fetched_page_supersedes_overlap_without_fabricated_wording(archive, monkeypatch):
    before = store.now() - timedelta(hours=1)
    estimator.record_capture(packet([message(before)]), before)
    at, value, status, calls = collect(monkeypatch, 'In 20 carts')
    assert status == 'purchase_message_unavailable'
    assert not any(r['metric'] == 'purchase_message' for r in value['observations'])
    prior = estimator.calculate('123', (before + timedelta(seconds=1)).isoformat())
    assert len(prior['purchase_evidence']) == 1
    current = estimator.calculate('123')
    assert current['value'] is None and current['purchase_evidence'] == []
    assert 'missing_or_conflicting_purchase_message' in current['issues']
    with store.database() as con:
        latest = json.loads(con.execute('SELECT payload FROM estimator_evidence ORDER BY captured_at DESC LIMIT 1').fetchone()[0])
    assert latest['attributes']['purchase_message_captured_at'] == at.isoformat()
    assert latest['attributes']['purchase_message_status'] == status
    assert not any(r['metric'] == 'purchase_message' for r in latest['observations'])


def test_absent_page_permission_does_not_emit_a_missing_capture_or_extra_call(archive, monkeypatch):
    before = store.now() - timedelta(hours=1)
    estimator.record_capture(packet([message(before)]), before)
    at, value, status, calls = collect(monkeypatch, '', scopes={'listing_api'})
    assert status == 'api_updated'
    assert len(calls) == 2 and all(scope == 'listing_api' for _, scope in calls)
    result = estimator.calculate('123')
    assert len(result['purchase_evidence']) == 1 and result['value'] is None
    with store.database() as con:
        latest = json.loads(con.execute('SELECT payload FROM estimator_evidence ORDER BY captured_at DESC LIMIT 1').fetchone()[0])
    assert 'purchase_message_status' not in latest.get('attributes', {})


@pytest.mark.parametrize('raw', ['12 people bought this in the past 24 hours', 'In 20 carts'])
def test_page_time_is_not_backdated_to_cached_review_window(archive, monkeypatch, raw):
    review_end = store.now() - timedelta(days=2)
    at, value, status, calls = collect(monkeypatch, raw,
        scopes={'listing_api', 'listing_reviews', 'listing_pages'}, cached_review_end=review_end)
    with store.database() as con:
        saved = json.loads(con.execute('SELECT payload FROM estimator_evidence').fetchone()[0])
    assert int(store.stamp(saved['review_window']['end']).timestamp()) == int(review_end.timestamp())
    assert saved['review_window']['end'] != at.isoformat()
    assert saved['attributes']['purchase_message_captured_at'] == at.isoformat()
    messages = [r for r in value['observations'] if r['metric'] == 'purchase_message']
    if status == 'purchase_message_observed':
        assert store.stamp(messages[0]['observed_at']) == at
        assert estimator.calculate('123')['purchase_evidence'][0]['window_end'] == at.isoformat()
    else:
        assert not messages
        assert estimator.calculate('123')['purchase_evidence'] == []
