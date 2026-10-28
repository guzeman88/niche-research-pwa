"""Isolated saved-evidence integration; no provider requests or live databases."""
from collections import Counter
from contextlib import closing
from datetime import timedelta
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from services.sales_intelligence import anchored, estimator, store


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setenv('VALIDATION_DB_PATH', str(tmp_path / 'ledger.sqlite'))
    monkeypatch.setenv('SALES_INTELLIGENCE_ROOT', str(tmp_path / 'archive'))
    monkeypatch.setenv('APP_KEYWORD_FEED_ROOT', str(tmp_path / 'native'))
    at = store.now().replace(microsecond=0) - timedelta(seconds=2)
    monkeypatch.setattr(store, 'now', lambda: at + timedelta(seconds=1))
    with store.database(True) as con:
        for identity in ('123', '456'):
            con.execute('INSERT INTO estimator_tracking VALUES(?,?,1)', (identity, at.isoformat()))
    return at


def save_capture(at, identity='123', shop_id='7', value=100, days_ago=0, times=None, complete=True,
                 source_ref=None, available_at=None, title=None):
    captured = at - timedelta(days=days_ago)
    ref = source_ref or 'https://api.etsy.com/v3/application/shops/' + shop_id
    packet = {'listings': [{'listing_id': identity, 'title': title or 'Product ' + identity,
        'shop': 'Same display name', 'source': 'etsy_public', 'source_ref': 'https://www.etsy.com/listing/' + identity}],
        'observations': [{'listing_id': identity, 'metric': 'shop_sales', 'value': value,
            'observed_at': captured.isoformat(), 'basis': 'lifetime', 'source': 'etsy_public', 'source_ref': ref, 'precision': 'exact'}]}
    window = {'start': (captured - timedelta(days=30)).isoformat(), 'end': captured.isoformat(),
              'complete': complete, 'review_times': times or [], 'observed_reviews': len(times or [])}
    identity_hash = estimator.record_capture(packet, captured, window,
                                             attributes={'shop_id': shop_id, 'state': 'active'})
    if available_at:
        with store.database(True) as con:
            con.execute('UPDATE estimator_evidence SET available_at=? WHERE id=?', (available_at.isoformat(), identity_hash))
    return identity_hash


def seed(at):
    event = (at - timedelta(hours=12)).isoformat()
    for identity in ('123', '456'):
        save_capture(at, identity, value=100, days_ago=3)
        save_capture(at, identity, value=130, times=[event] * (2 if identity == '123' else 1))


def test_saved_shop_evidence_joint_allocation_and_separate_legacy_value(archive):
    seed(archive)
    original = estimator.calculate('123')['value']
    summary = anchored.rebuild()
    result = anchored.overview()
    assert summary['anchored_shops'] == 1
    assert len(result['shops']) == 1
    shop = result['shops'][0]
    assert shop['window']['counter_delta'] == 30
    assert shop['window']['days'] == 3
    assert sum(p['value'] or 0 for p in shop['products']) + shop['unobserved']['value'] == pytest.approx(30)
    assert shop['unobserved']['value'] > 0
    assert all(p['unit'] == 'shop_counter_increments' for p in result['items'])
    assert result['accuracy'] == 'unvalidated'
    assert estimator.calculate('123')['value'] == original
    assert result['validation']['status'] == 'counter_unit_verification_required'
    with store.database() as con:
        assert con.execute("SELECT count(*) FROM snapshots WHERE kind='shop_allocation'").fetchone()[0] == 2
    anchored.rebuild()
    with store.database() as con:
        assert con.execute("SELECT count(*) FROM snapshots WHERE kind='shop_allocation'").fetchone()[0] == 2


def test_same_display_name_does_not_merge_different_exact_shops(archive):
    for identity, shop in [('123', '7'), ('456', '8')]:
        save_capture(archive, identity, shop, days_ago=2)
        save_capture(archive, identity, shop, value=110, times=[(archive - timedelta(hours=1)).isoformat()])
    with store.database() as con:
        result = anchored.build(con, catalog_snapshots=[])
    assert {s['shop_id'] for s in result['shops']} == {'7', '8'}
    assert all(len(s['products']) == 1 for s in result['shops'])


def test_no_future_or_late_available_capture_and_readonly_replay(archive):
    seed(archive)
    save_capture(archive, value=9999, days_ago=-1)
    save_capture(archive, value=9998, available_at=archive + timedelta(days=1))
    with store.database() as con:
        path = con.execute('PRAGMA database_list').fetchone()[2]
    with closing(sqlite3.connect('file:' + path + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        result = anchored.build(con, archive.isoformat(), catalog_snapshots=[])
    assert result['shops'][0]['window']['counter_delta'] == 30
    with pytest.raises(ValueError, match='future'):
        with store.database() as con:
            anchored.build(con, (archive + timedelta(days=2)).isoformat(), catalog_snapshots=[])


def test_review_multiplicity_dedup_partial_unknown_and_catalog_members(archive):
    event = (archive - timedelta(hours=12)).isoformat()
    save_capture(archive, days_ago=3, value=100)
    save_capture(archive, days_ago=1, value=110, times=[event, event])  # future event outside this window ignored
    save_capture(archive, value=120, times=[event, event])
    with store.database() as con:
        history, events, coverage, _ = anchored._read_history(con, '123', archive.isoformat())
        assert Counter(events)[event] == 2
        result = anchored.build(con, catalog_snapshots=[{'shop_id': '7', 'captured_at': archive.isoformat(),
            'listing_ids': ['123', '789'], 'public_complete': True, 'active_count': 2}])
    shop = result['shops'][0]
    assert {p['listing_id'] for p in shop['products']} == {'123', '789'}
    assert shop['catalog_context']['public_complete'] is True
    assert shop['unobserved']['value'] > 0  # active catalog is never a lifetime census


def test_legacy_url_identity_alias_requires_same_capture_numeric_proof(archive):
    ref = 'https://www.etsy.com/shop/ExactShop'
    save_capture(archive, days_ago=2, source_ref=ref)
    save_capture(archive, value=120, source_ref=ref, times=[(archive-timedelta(hours=1)).isoformat()])
    with store.database() as con:
        result = anchored.build(con, catalog_snapshots=[])
    assert result['shops'][0]['shop_id'] == '7'
    assert result['shops'][0]['window']['counter_delta'] == 20
    assert anchored._shop_reference('https://untrusted.example/shop/ExactShop') is None
    assert anchored._shop_reference('https://etsy.com@untrusted.example/shop/ExactShop') is None


def test_frozen_label_evaluation_requires_units_exact_window_and_unseen_labels(archive):
    start, end = (archive - timedelta(days=3)).isoformat(), archive.isoformat()
    prediction = {'listing_id': '123', 'shop_id': '7', 'value': 20, 'window': {'start': start, 'end': end},
                  'frozen_at': (archive + timedelta(seconds=1)).isoformat()}
    label = {'listing_id': '123', 'shop_id': '7', 'actual': 21, 'unit': 'purchases', 'period_start': start,
             'period_end': end, 'available_at': (archive+timedelta(days=1)).isoformat(),
             'source_ref': 'Redacted seller order export', 'attestation': 'Seller attests this is a real order export'}
    mapping = {'verified': True, 'unit': 'purchases', 'source_ref': 'Independent semantics verification fixture'}
    assert anchored.evaluate_frozen([prediction], [label])['matched_cases'] == 0
    report = anchored.evaluate_frozen([prediction], [label], mapping)
    assert report['mae'] == 1 and report['matched_cases'] == 1
    assert report['within_five_percent'] == 1
    assert anchored.evaluate_frozen([prediction], [{**label, 'unit': 'units'}], mapping)['matched_cases'] == 0
    assert anchored.evaluate_frozen([prediction], [{**label, 'period_start': end}], mapping)['matched_cases'] == 0
    assert anchored.evaluate_frozen([prediction], [{**label, 'available_at': archive.isoformat()}], mapping)['matched_cases'] == 0
    # Later recalculation cannot replace the first frozen prediction on this case.
    assert anchored.evaluate_frozen([prediction, {**prediction, 'value': 21,
        'frozen_at': (archive+timedelta(hours=1)).isoformat()}], [label], mapping)['mae'] == 1


def test_private_api_initial_and_materialized_results(archive, monkeypatch):
    from main import app
    monkeypatch.setenv('PIPELINE_API_TOKEN', 'isolated-secret')
    client = TestClient(app)
    assert client.get('/api/sales-intelligence/anchored').status_code == 401
    headers = {'Authorization': 'Bearer isolated-secret'}
    first = client.get('/api/sales-intelligence/anchored', headers=headers)
    assert first.status_code == 200 and 'no-store' in first.headers['cache-control']
    assert first.json()['summary']['status'] == 'awaiting_backend_calculation'
    seed(archive)
    anchored.rebuild()
    result = client.get('/api/sales-intelligence/anchored', headers=headers).json()
    assert result['summary']['anchored_shops'] == 1
    assert len(result['items']) == 2
    assert 'review_times' not in json.dumps(result)


def test_stale_report_cannot_remain_current(archive, monkeypatch):
    seed(archive)
    anchored.rebuild()
    monkeypatch.setattr(store, 'now', lambda: archive + timedelta(days=8))
    report = anchored.overview()
    assert report['summary']['allocated_products'] == 0
    assert all(i['value'] is None for i in report['items'])
    assert all(p['value'] is None for s in report['shops'] for p in s['products'])
    assert report['summary']['anchored_shops']==0
    assert all(s['window'] is None for s in report['shops'])


def test_counter_can_expire_before_materialization_itself(archive,monkeypatch):
    save_capture(archive,days_ago=5,value=100)
    save_capture(archive,days_ago=2,value=130,times=[(archive-timedelta(days=3)).isoformat()])
    anchored.rebuild()
    assert anchored.overview()['summary']['allocated_products']>0
    monkeypatch.setattr(store,'now',lambda:archive+timedelta(days=6))
    report=anchored.overview()
    assert report['summary']['allocated_products']==0
    assert report['summary']['anchored_shops']==0
