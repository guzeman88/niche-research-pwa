"""Shop-counter constrained, deliberately uncalibrated product allocations.

No network, database, fitted provider label or purchase-unit conversion occurs
here.  A counter increment is the measured unit.  Reviews are assumed delayed
Poisson observations of latent allocations.  A Dirichlet shrinkage prior and an
explicit unobserved category keep sparse catalog samples from claiming every
shop increment.  Nuisance-parameter scenarios are sensitivity checks, never
confidence intervals or evidence of product-sales accuracy.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math

VERSION = 'etgen-shop-allocation-v1'
UTC = timezone.utc
DAY = 86400.0
DEFAULTS = {
    'catalog_complete': False,
    'review_rates': [.02, .10, .30],
    'lag_days': [0, 7, 14, 28],
    'min_interval_hours': 24,
    'max_staleness_days': 7,
    'prior_strength': 5.0,
    'central_review_rate': .10,
    'central_lag_days': 0,
}
ASSUMPTIONS = [
    'Shop counter increments are not verified purchases, buyers or units.',
    'Review probability, review lag and catalog completeness are uncalibrated assumptions.',
    'The central allocation assumes a 10% review probability and zero review delay unless configured otherwise.',
    'Each scenario assumes a fixed review lag and stable allocation shares within the observed counter window.',
    'Future reviews are unavailable; delayed scenarios are right censored at the evidence cutoff.',
    'Reviews can concern earlier sales; stock changes, prices and inactive status do not establish sales.',
    'Sensitivity ranges are not confidence intervals; without product-level outcomes the full feasible range remains zero to the shop increment.',
    'Reconciling a shop total is a model constraint, not independent validation.',
]


def _stamp(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Evidence timestamps must include a timezone')
    return parsed.astimezone(UTC)


def _number(value, minimum=0, maximum=1e15):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and minimum <= value <= maximum else None


def _config(raw):
    config = {**DEFAULTS, **(raw or {})}
    if not isinstance(config['catalog_complete'], bool):
        raise ValueError('catalog_complete must be a boolean')
    for field, low, high in [('min_interval_hours', 1, 720), ('max_staleness_days', 0, 30),
                             ('prior_strength', .01, 1000), ('central_review_rate', .0001, 1),
                             ('central_lag_days', 0, 90)]:
        if _number(config[field], low, high) is None:
            raise ValueError('Unsupported allocation configuration: ' + field)
    for field, low, high in [('review_rates', .0001, 1), ('lag_days', 0, 90)]:
        values = config[field]
        if not isinstance(values, (list, tuple)) or not values or len(values) > 12:
            raise ValueError('Use one to twelve sensitivity values for ' + field)
        if any(_number(value, low, high) is None for value in values):
            raise ValueError('Unsupported sensitivity value: ' + field)
        central = config['central_review_rate' if field == 'review_rates' else 'central_lag_days']
        config[field] = sorted(set(float(x) for x in values) | {float(central)})
    return config


def _counter_window(rows, at, config, issues):
    if len(rows) > 20000:
        raise ValueError('Use at most 20,000 shop counter readings')
    by_time = defaultdict(list)
    for row in rows:
        try:
            observed = _stamp(row['observed_at'])
            available = _stamp(row.get('available_at') or row['observed_at'])
        except (KeyError, TypeError, ValueError, OverflowError):
            issues.add('invalid_counter_timestamp')
            continue
        if observed > at or available > at:
            issues.add('future_or_late_available_counter_excluded')
            continue
        if observed < at - timedelta(days=30):
            continue
        value = _number(row.get('value'))
        # This counter reports whole numbers; fractional values are unsupported.
        if value is None or value != int(value):
            value = None
            issues.add('invalid_counter_value')
        by_time[observed].append(value)
    run = []
    for observed, values in sorted(by_time.items()):
        unique = set(values)
        if len(unique) != 1 or None in unique:
            issues.add('conflicting_or_missing_shop_counter')
            run = []
            continue
        value = values[0]
        if run and value < run[-1][1]:
            issues.add('decreased_shop_counter_interval_quarantined')
            run = []
        run.append((observed, value))
    if not run:
        return None, 'awaiting_shop_counter'
    if at - run[-1][0] > timedelta(days=config['max_staleness_days']):
        return None, 'stale_shop_counter'
    if len(run) < 2 or (run[-1][0] - run[0][0]).total_seconds() < config['min_interval_hours'] * 3600:
        return None, 'needs_longer_counter_window'
    start, before = run[0]
    end, after = run[-1]
    return {'start': start.isoformat(), 'end': end.isoformat(),
            'days': (end - start).total_seconds() / DAY,
            'counter_delta': int(after - before), 'readings': len(run)}, None


def _intervals(raw, at, issues):
    result = []
    for item in raw:
        # An incomplete response is never converted to a zero-review interval.
        if item.get('complete') is not True:
            issues.add('incomplete_review_coverage')
            continue
        try:
            start, end = _stamp(item['start']), _stamp(item['end'])
            available = _stamp(item.get('available_at') or item['end'])
        except (KeyError, TypeError, ValueError, OverflowError):
            issues.add('invalid_review_coverage')
            continue
        if available > at or end > at or end <= start:
            issues.add('future_or_invalid_review_coverage_excluded')
            continue
        result.append((start, end))
    merged = []
    for start, end in sorted(result):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _engagement(product, start, end, issues):
    """Only a weak prior modifier from an explicitly aligned measured change."""
    weight = 1.0
    for field in ('views_change', 'favorites_change'):
        item = product.get(field)
        if item is None:
            continue
        if not isinstance(item, dict):
            issues.add('unaligned_engagement_ignored')
            continue
        try:
            aligned = (_stamp(item['start']) == start and _stamp(item['end']) == end
                       and item.get('complete') is True)
        except (KeyError, TypeError, ValueError, OverflowError):
            aligned = False
        value = _number(item.get('value'))
        if not aligned or value is None:
            issues.add('unaligned_engagement_ignored')
            continue
        weight += min(.125, math.log1p(value) / 100)
    return weight


def _prepare(products, start, end, at, lags):
    if len(products) > 600:
        raise ValueError('Use at most 600 observed products per shop')
    prepared, seen = [], set()
    event_budget = 0
    for product in products:
        identity = str(product.get('listing_id', '')).strip()
        if not identity or len(identity) > 80 or identity in seen:
            raise ValueError('Product listing IDs must be distinct and nonempty')
        seen.add(identity)
        issues = set()
        metadata_at = product.get('metadata_at')
        metadata_valid = True
        if metadata_at:
            try:
                metadata_valid = _stamp(metadata_at) <= at
            except (ValueError, TypeError, OverflowError):
                metadata_valid = False
            if not metadata_valid:
                issues.add('future_or_invalid_metadata_ignored')
        ranges = _intervals(product.get('review_coverage') or [], at, issues)
        times = []
        raw_times = product.get('review_times') or []
        event_budget += len(raw_times)
        if event_budget > 200000:
            raise ValueError('Use at most 200,000 normalized review events per shop')
        for item in raw_times:
            try:
                when = _stamp(item['observed_at'] if isinstance(item, dict) else item)
                available = _stamp(item.get('available_at') or item['observed_at']) if isinstance(item, dict) else when
            except (KeyError, ValueError, TypeError, OverflowError):
                issues.add('invalid_review_event')
                continue
            if when > at or available > at:
                issues.add('future_or_late_available_review_excluded')
                continue
            times.append(when)
        evidence = {}
        for lag in lags:
            left, right = start + timedelta(days=lag), end + timedelta(days=lag)
            seconds = sum(max(0, (min(right, b, at) - max(left, a)).total_seconds()) for a, b in ranges)
            fraction = min(1.0, seconds / (end - start).total_seconds())
            count = sum(left < when <= right and any(a < when <= b for a, b in ranges) for when in times)
            evidence[lag] = {'count': count, 'fraction': fraction,
                             'right_censored': right > at}
        prepared.append({'listing_id': identity, 'evidence': evidence,
                         'weight': _engagement(product, start, end, issues) if metadata_valid else 1.0,
                         'issues': issues, 'state': product.get('state') if metadata_valid else None})
    return prepared


def _mode(total, counts, detection, prior, strength):
    """Constrained MAP for Poisson counts and Dirichlet(1 + strength*prior).

    The objective is sum((count + strength*prior)*log(share)
    - total*detection*share), with nonnegative shares summing to one.
    The unknown category has detection zero, so the unique Lagrange root is
    positive. This is an allocation model, not learned sales calibration.
    """
    if total == 0:
        return [0.0] * len(prior)
    numerators = [count + strength * p for count, p in zip(counts, prior)]
    penalties = [total * q for q in detection]
    low, high = 0.0, sum(numerators) + 1.0
    for _ in range(80):
        middle = (low + high) / 2
        mass = sum(a / (middle + penalty) for a, penalty in zip(numerators, penalties))
        if mass > 1:
            low = middle
        else:
            high = middle
    shares = [a / ((low + high) / 2 + penalty) for a, penalty in zip(numerators, penalties)]
    normalization = sum(shares)
    result = [total * share / normalization for share in shares]
    # The unobserved residual makes floating-point mass conservation explicit.
    result[-1] = max(0.0, total - sum(result[:-1]))
    return result


def allocate(shop_id, counter_readings, products, as_of=None, config=None):
    """Allocate an observed shop-counter window without converting its units.

    Inputs are source-normalized, already deduplicated event occurrences.
    Repeated timestamps may represent different reviews and retain multiplicity.
    Counter readings are instead deduplicated by timestamp; conflicts break the
    usable run. All endpoint intervals are exact, with no 30-day extrapolation.
    """
    at = _stamp(as_of) if as_of is not None else datetime.now(UTC)
    settings = _config(config)
    issues = set()
    window, status = _counter_window(counter_readings, at, settings, issues)
    result = {'version': VERSION, 'shop_id': str(shop_id), 'as_of': at.isoformat(),
              'status': status, 'window': window, 'unit': 'shop_counter_increments',
              'products': [], 'unobserved': {'value': None, 'low': None, 'high': None},
              'issues': [], 'diagnostics': {}, 'assumptions': list(ASSUMPTIONS),
              'validation': 'unvalidated',
              'range_type': 'assumption_sensitivity_not_confidence_interval', 'priority': []}
    if not window:
        for product in products:
            result['products'].append({'listing_id': str(product.get('listing_id', '')),
                                       'value': None, 'low': None, 'high': None,
                                       'status': status, 'issues': []})
            result['priority'].append({'listing_id': str(product.get('listing_id', '')),
                                       'reason': status, 'score': 1.0})
        result['issues'] = sorted(issues)
        return result
    start, end = _stamp(window['start']), _stamp(window['end'])
    prepared = _prepare(products, start, end, at, settings['lag_days'])
    total = window['counter_delta']
    unknown_priors = [.05, .10, .25] if settings['catalog_complete'] else [.25, .50, .75]
    central_unknown = .10 if settings['catalog_complete'] else .50
    if not settings['catalog_complete']:
        issues.add('catalog_incomplete_unobserved_sales_retained')
    if not prepared:
        result.update(status='insufficient_product_evidence', unobserved={'value': total, 'low': total, 'high': total})
        result['issues'] = sorted(issues | {'no_observed_products'})
        return result
    scenarios, allocations = [], []
    central = None
    has_signal = any(e['count'] > 0 for p in prepared for e in p['evidence'].values())
    weights = [p['weight'] for p in prepared]
    for rate in settings['review_rates']:
        for lag in settings['lag_days']:
            evidence = [p['evidence'][lag] for p in prepared]
            counts = [e['count'] for e in evidence] + [0]
            detection = [rate * e['fraction'] for e in evidence] + [0.0]
            if any(e['right_censored'] for e in evidence):
                issues.add('delayed_reviews_right_censored')
            if sum(counts) > total:
                issues.add('review_model_scope_or_lag_conflict')
            for unknown_prior in unknown_priors:
                prior = [(1 - unknown_prior) * weight / sum(weights) for weight in weights] + [unknown_prior]
                values = _mode(total, counts, detection, prior, settings['prior_strength'])
                allocations.append(values)
                scenarios.append({'review_rate': rate, 'lag_days': lag,
                                  'unobserved_prior': unknown_prior,
                                  'observed_reviews': sum(counts),
                                  'allocated': sum(values[:-1]), 'unobserved': values[-1],
                                  'total': sum(values),
                                  'review_exposure_fraction': sum(e['fraction'] for e in evidence) / len(evidence)})
                if (rate == settings['central_review_rate'] and lag == settings['central_lag_days']
                        and unknown_prior == central_unknown):
                    central = values
    if not has_signal and total:
        # Absence of reviews is not a product-sales zero or a basis for dividing
        # the whole shop by the number of observed products.
        issues.add('no_positive_product_review_signal')
        central = [0.0] * len(prepared) + [float(total)]
    result['status'] = ('zero_shop_counter_change' if not total else
                        'ambiguous_allocation' if has_signal else 'insufficient_product_evidence')
    for i, product in enumerate(prepared):
        central_evidence = product['evidence'][settings['central_lag_days']]
        coverage = central_evidence['fraction']
        product_issues = set(product['issues'])
        if coverage < 1 - 1e-9:
            product_issues.add('review_period_partly_unobserved')
        if product['state'] in ('inactive', 'sold_out', 'removed', 'expired', 'draft'):
            product_issues.add('inactive_now_does_not_resolve_historical_sales')
        low = min(values[i] for values in allocations)
        high = max(values[i] for values in allocations)
        value = central[i] if has_signal or total == 0 else None
        if value is not None:
            low, high = min(low, value), max(high, value)
        product_status = ('zero_shop_counter_change' if not total else
                          'ambiguous_allocation' if central_evidence['count'] else
                          'prior_only_allocation' if has_signal else 'insufficient_product_evidence')
        row = {'listing_id': product['listing_id'], 'value': value,
               'low': low if has_signal or not total else 0.0,
               'high': high if has_signal or not total else float(total),
               'status': product_status, 'review_count': central_evidence['count'],
               'review_coverage_fraction': coverage if coverage else None,
               'feasible_low': 0.0, 'feasible_high': float(total),
               'issues': sorted(product_issues)}
        result['products'].append(row)
        width = (row['high'] - row['low']) / max(1, total)
        result['priority'].append({'listing_id': product['listing_id'],
                                   'reason': 'missing_review_coverage' if coverage < .99 else 'allocation_uncertainty',
                                   'score': min(1.0, max(width, 1 - coverage))})
    unknown_values = [values[-1] for values in allocations] + [central[-1]]
    result['unobserved'] = {'value': central[-1], 'low': min(unknown_values), 'high': max(unknown_values)}
    result['priority'].sort(key=lambda item: (-item['score'], item['listing_id']))
    result['diagnostics'] = {
        'method': 'constrained_poisson_dirichlet_posterior_mode',
        'catalog_complete': settings['catalog_complete'],
        'product_count': len(prepared), 'scenario_count': len(scenarios),
        'central_review_rate': settings['central_review_rate'],
        'central_lag_days': settings['central_lag_days'],
        'central_unobserved_prior': central_unknown,
        'prior_strength': settings['prior_strength'],
        'central_reconciled_total': sum(value for value in central),
        'all_scenarios_reconcile': all(abs(s['total'] - total) <= 1e-8 * max(1, total) for s in scenarios),
        'independent_validation': False, 'scenarios': scenarios,
    }
    result['issues'] = sorted(issues)
    return result
