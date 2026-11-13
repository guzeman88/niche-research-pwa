"""Isolated numerical, provenance, leakage and mutation regression tests."""
from datetime import datetime, timezone, timedelta
import json
import math
import pytest
from pydantic import ValidationError
from models.selling_products import SalesConfig, Observation, Packet
from services import sales_model as model, selling_products as service

AT = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def listing(identity='one', shop='Shop A'):
    return {'listing_id': identity, 'title': 'Original weekly planner', 'shop': shop, 'source_ref': 'Isolated listing'}


def obs(metric, value, days=0, **extra):
    return {'listing_id': 'one', 'metric': metric, 'value': value,
            'basis': 'point_in_time' if metric in ('purchase_message', 'carts', 'stock', 'price') else 'lifetime',
            'observed_at': (AT - timedelta(days=days)).isoformat(), 'source': 'manual', 'source_ref': 'Isolated fixture', **extra}


def message(value=7, days=0, **extra):
    return obs('purchase_message', value, days, unit='buyers', precision='exact', window_hours=24,
               raw_message=f'{value} people bought this in the past 24 hours', **extra)


def run(observations=(), config=None, listings=None, **extra):
    settings = SalesConfig.model_validate(config or {}).model_dump(mode='json')
    return model.run(listings=listings or [listing()], observations=list(observations), reviews=[], patterns=[], config=settings, at=AT, **extra)


def test_no_default_sales_or_fake_opportunity_score():
    result = run([obs('favorites', 500), obs('stock', 5), obs('carts', 10)])
    assert result['status'] == 'needs_evidence'
    assert result['listings'][0]['windows']['7']['estimate'] is None
    assert result['opportunity']['score'] is None
    assert result['opportunity']['missing']


def test_parser_preserves_units_bounds_and_never_parses_carts():
    parsed = model.parse_message('In demand. 1,200+ people bought this in the last 24 hours')
    assert (parsed['value'], parsed['unit'], parsed['precision']) == (1200, 'buyers', 'lower_bound')
    assert model.parse_message('Over 20 people bought this in the past 24 hours')['precision'] == 'lower_bound'
    for raw in ['In 20 carts', 'Bestseller', 'unknown', '7 people bought this last year', 'Not 7 people bought this in the last 24 hours', '7 people bought this in the last 0 hours']:
        with pytest.raises(ValueError):
            model.parse_message(raw)


def test_message_cannot_be_misrepresented_as_units_or_different_count():
    Observation.model_validate(message())
    for key, value in [('value', 100), ('unit', 'purchases'), ('precision', 'lower_bound'), ('window_hours', 48)]:
        with pytest.raises(ValidationError):
            Observation.model_validate({**message(), key: value})


def test_buyers_are_observed_but_not_silently_converted():
    result = run([message(days=i) for i in range(7)])['listings'][0]
    assert len(result['purchase_evidence']) == 7
    assert result['windows']['7']['estimate'] is None
    result = run([message(days=i) for i in range(7)], config={'purchases_per_buyer': 1, 'assumptions_note': 'Assume one purchase per buyer for this scenario.'})['listings'][0]
    assert result['windows']['7']['estimate'] == 49
    assert result['windows']['7']['coverage_days'] == 7
    assert result['windows']['30']['estimate'] is None


def test_overlapping_and_duplicate_messages_do_not_inflate_sales():
    data = [message(days=i / 2) for i in range(14)]
    config = {'purchases_per_buyer': 1, 'assumptions_note': 'Isolated scenario conversion assumption.'}
    result = run(data + data, config=config)['listings'][0]
    assert result['windows']['7']['estimate'] == 49
    assert len(result['purchase_evidence']) == 7
    assert 'overlapping_purchase_windows_not_added' in result['issues']


def test_lower_bounds_conflicts_and_missing_are_not_exact_anchors():
    data = [message(days=i) for i in range(7)]
    data.append({**data[0], 'value': None})
    data[2] = {**data[2], 'precision': 'lower_bound'}
    result = run(data)['listings'][0]
    assert result['windows']['7']['estimate'] is None
    assert 'missing_or_conflicting_purchase_message' in result['issues']
    assert all(x['value'] is not None for x in result['purchase_evidence'])


def test_future_data_does_not_enter_features_or_predictions():
    before = model.features(listing(), [], [listing()], AT)
    after = model.features(listing(), [obs('carts', 999, days=-1), obs('views', 1000, days=-1), message(days=-1)], [listing()], AT)
    assert before == after


def test_reviews_shift_backwards_instead_of_becoming_same_day_sales():
    observations = [obs('reviews', 0, days=7), obs('reviews', 7)]
    config = {'review_rate': 0.2, 'review_delay_min': 0, 'review_delay_max': 0, 'assumptions_note': 'Isolated measured-like review scenario.'}
    result = run(observations, config=config)['listings'][0]['windows']['7']
    assert result['estimate'] == 35
    config.update(review_delay_min=30, review_delay_max=30)
    result = run(observations, config=config)['listings'][0]['windows']['7']
    assert result['estimate'] is None


def test_shop_ratio_requires_matching_timestamps_and_never_allocates_shop_sales():
    data = [obs('shop_sales', 1000), obs('shop_reviews', 200)]
    result = run(data)['listings'][0]
    assert result['review_rate'] == 0.2
    assert result['windows']['7']['estimate'] is None
    data[-1]['observed_at'] = (AT - timedelta(days=1)).isoformat()
    assert run(data)['listings'][0]['review_rate'] is None


def test_counter_decrease_missing_and_duplicate_shop_totals():
    values = [obs('reviews', 10, days=7), obs('reviews', 5), obs('shop_sales', 1000, days=7), obs('shop_sales', 1010)]
    result = run(values, config={'review_rate': .2, 'assumptions_note': 'Explicit test scenario assumption.'})['listings'][0]
    assert result['windows']['7']['estimate'] is None
    assert 'decreased_reviews' in result['issues']
    assert result['shop_changes'][0]['net_change'] == 10
    values.append({**obs('shop_sales', 1010), 'listing_id': 'two'})
    assert run(values, listings=[listing(), listing('two')])['listings'][0]['shop_changes'][0]['net_change'] == 10


def test_view_conversion_uses_change_not_lifetime_and_needs_assumption():
    data = [obs('views', 1000, days=7), obs('views', 1700)]
    assert run(data)['listings'][0]['windows']['7']['estimate'] is None
    result = run(data, config={'view_conversion': .05, 'assumptions_note': 'Explicit conversion rate for fixture.'})['listings'][0]['windows']['7']
    assert result['estimate'] == 35


def test_unknown_rates_zero_and_nonfinite_parameters():
    for data in [{'review_rate': 0}, {'review_rate': True}, {'baseline_daily': float('nan')}, {'review_delay_min': 30, 'review_delay_max': 2}, {'seasonality': [True] * 12}, {'purchases_per_buyer': .5}, {'baseline_daily': 10}]:
        with pytest.raises(ValueError):
            SalesConfig.model_validate(data)
    result = run(config={'baseline_daily': 0, 'assumptions_note': 'Zero baseline for scenario test only.'})['listings'][0]['windows']['7']
    assert result['estimate'] == 0
    assert result['high'] > 0
    assert result['coverage_days'] == 0


def calibration_data():
    listings, observations, cases = [], [], []
    # Six earlier training shops, two later held-out shops; four windows per shop.
    for shop in range(8):
        for index in range(4):
            identity = f'{shop}-{index}'
            listings.append(listing(identity, f'Fixture shop {shop}'))
            start = AT - timedelta(days=80 if shop < 6 else 20)
            end = start + timedelta(days=6)
            count = 2 ** (index + 1)
            observations.extend([{**obs('carts', count), 'listing_id': identity, 'observed_at': end.isoformat()}])
            cases.append({'case_id': identity, 'listing_id': identity, 'period_start': start.date().isoformat(),
                'period_end': end.date().isoformat(), 'actual_purchases': count * 7,
                'source_ref': 'Isolated transaction fixture', 'note': 'Synthetic purchase counts, not real sales.'})
    return listings, observations, cases


def test_training_holds_out_shops_and_time_and_reports_baseline():
    listings, observations, cases = calibration_data()
    result = model.train(listings, observations, cases)
    report = result['validation']
    assert report['training_cases'] == 24
    assert report['test_cases'] == 8 and report['test_shops'] == 2
    assert math.isfinite(report['mae_daily'])
    assert result['active'] == (report['mae_daily'] < report['baseline_mae_daily'])
    assert report['coverage_claim'] is None
    # A future observation cannot change fitted coefficients or test predictions.
    future = {**obs('carts', 1000000, days=-1), 'listing_id': listings[0]['listing_id']}
    second = model.train(listings, observations + [future], cases)
    assert result['coefficients'] == second['coefficients']
    assert report == second['validation']


def test_training_refuses_leaky_splits_insufficient_cases_and_overlaps():
    listings, observations, cases = calibration_data()
    with pytest.raises(ValueError):
        model.train(listings, observations, cases[:10])
    same_shop = [{**row, 'shop': 'Same shop'} for row in listings]
    with pytest.raises(ValueError):
        model.train(same_shop, observations, cases)
    cases.append({**cases[0], 'case_id': 'overlap'})
    with pytest.raises(ValueError, match='overlap'):
        model.train(listings, observations, cases)


def test_training_candidate_stays_inactive_when_baseline_is_better():
    listings, observations, cases = calibration_data()
    result = model.train(listings, observations, [{**c, 'actual_purchases': 0} for c in cases])
    assert not result['active']
    assert result['validation']['baseline_mae_daily'] == 0


def test_stale_purchase_messages_do_not_supply_current_persistence():
    result = run([message(days=45)])
    assert result['opportunity']['components']['persistence'] is None


def test_estimates_cannot_extend_before_declared_listing_creation():
    created = (AT - timedelta(days=20)).date().isoformat()
    result = run(listings=[{**listing(), 'created_on': created}], config={'baseline_daily': 3, 'assumptions_note': 'Synthetic baseline for age regression.'})['listings'][0]['windows']['30']
    assert result['active_days'] == 20.5
    assert result['estimate'] == 61.5
    assert result['extrapolated_days'] == 0
    young = run(listings=[{**listing(), 'created_on': AT.date().isoformat()}], config={'baseline_daily': 3, 'assumptions_note': 'Synthetic baseline for new listing.'})['listings'][0]['windows']['7']
    assert young['estimate'] is None and young['active_days'] == 0.5


@pytest.fixture
def opportunity(tmp_path, monkeypatch):
    monkeypatch.setenv('VALIDATION_DB_PATH', str(tmp_path / 'private.sqlite'))
    return service.save_opportunity({'name': 'Model test', 'keyword': 'teacher planner'})


def test_config_revision_conflicts_and_export_preserve_old_evidence(opportunity):
    item = service.configure_model(opportunity['id'], {'expected_fingerprint': opportunity['fingerprint'], 'config': {'baseline_daily': 2, 'assumptions_note': 'Synthetic baseline for preservation test.'}})
    assert item['revision_count'] == 2
    with pytest.raises(service.Conflict):
        service.configure_model(item['id'], {'expected_fingerprint': opportunity['fingerprint'], 'config': {}})
    export = service.export(item['id'])
    assert export['analysis']['sales_model']['config']['baseline_daily'] == 2
    assert export['checksum']
    assert not export['can_publish']


def test_case_imports_are_atomic_idempotent_and_model_stales(opportunity):
    listings, observations, cases = calibration_data()
    item = service.import_packet(opportunity['id'], {'expected_fingerprint': opportunity['fingerprint'], 'packet': {'listings': listings, 'observations': observations, 'calibration': cases}})['opportunity']
    fitted = service.train_model(item['id'], {'expected_fingerprint': item['fingerprint']})
    assert fitted['analysis']['sales_model']['trained_model']['present']
    repeated = service.import_packet(item['id'], {'expected_fingerprint': fitted['fingerprint'], 'packet': {'calibration': cases}})['opportunity']
    assert repeated['revision_count'] == fitted['revision_count']
    changed = service.import_packet(item['id'], {'expected_fingerprint': repeated['fingerprint'], 'packet': {'observations': [{**observations[0], 'value': 999}]}})['opportunity']
    assert changed['analysis']['sales_model']['trained_model']['stale']
    assert changed['analysis']['sales_model']['trained_model']['active'] is False
    assert fitted['analysis']['sales_model']['trained_model']['artifact_id']


def test_calibration_csv_does_not_require_or_export_buyer_data():
    data = 'case_id,listing_id,period_start,period_end,actual_purchases,source_ref,note\na,one,2026-01-01,2026-01-07,7,Protected records,Counted listing purchase events\n'
    packet = service.parse_import({'format': 'csv', 'dataset': 'calibration', 'content': data})
    assert packet['calibration'][0]['actual_purchases'] == 7
    with pytest.raises(ValueError):
        Packet.model_validate({'calibration': [{**packet['calibration'][0], 'actual_purchases': True}]})


def test_new_endpoints_are_private(opportunity, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setenv('PIPELINE_API_TOKEN', 'fixture-token')
    client = TestClient(app)
    for path in ('/parse-purchase-message', '/opportunities/' + opportunity['id'] + '/model-config', '/opportunities/' + opportunity['id'] + '/calibrate'):
        assert client.post('/api/selling-products' + path, json={}).status_code == 401
    response = client.post('/api/selling-products/parse-purchase-message', json={'message': '7 people bought this in the last 24 hours'}, headers={'Authorization': 'Bearer fixture-token'})
    assert response.status_code == 200 and response.json()['unit'] == 'buyers'
    assert response.headers['cache-control'] == 'private, no-store'
