"""EtGen's local sales model. No network, paid dependencies or implicit training.

Counts, reporting units and windows stay separate. Default coefficients do not
pretend to be learned. Scenario envelopes are NOT statistical confidence bounds.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date, time
import hashlib
import json
import math
import re
from statistics import median

VERSION = 'etgen-sales-v1'
UTC = timezone.utc
DAY = 86400


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def stamp(value):
    return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(UTC)


def parse_message(raw):
    """Conservative English parser: never turn carts into sales or assume units."""
    match = re.fullmatch(r'(?:In demand[.!:]?\s*)?(?:(over|more than|at least)\s+)?((?:\d{1,3}(?:,\d{3})+|\d+))(\+)?\s+(people\s+)?bought\s+(?:this\s+)?in\s+the\s+(?:past|last)\s+(\d+)\s+hours?[.!]?', raw.strip(), re.I)
    if not match:
        raise ValueError('Message not recognized. Preserve and review the original purchase wording.')
    if not 1 <= int(match[5]) <= 168:
        raise ValueError('Purchase-message window must be between one hour and seven days')
    return {'value': int(match[2].replace(',', '')), 'precision': 'lower_bound' if match[1] or match[3] else 'exact',
            'unit': 'buyers' if match[4] else 'unknown', 'window_hours': int(match[5]),
            'raw_message': raw, 'metric': 'purchase_message', 'basis': 'point_in_time'}


def readings(rows, metric, until, listing_id=None, shop=None, listings=None):
    """One source-independent reading per timestamp. Conflicts/missing stay unknown."""
    grouped = defaultdict(list)
    by_id = {x['listing_id']: x for x in (listings or [])}
    for row in rows:
        if row['metric'] != metric or stamp(row['observed_at']) > until:
            continue
        if listing_id is not None and row['listing_id'] != listing_id:
            continue
        if shop is not None and by_id.get(row['listing_id'], {}).get('shop', '').strip().casefold() != shop:
            continue
        grouped[stamp(row['observed_at'])].append(row)
    result = []
    for at, group in sorted(grouped.items()):
        values = {x['value'] for x in group}
        same_currency = len({x.get('currency', '') for x in group}) == 1
        valid = len(values) == 1 and same_currency and None not in values and all(x.get('precision', 'exact') == 'exact' for x in group)
        result.append((at, group[0]['value'] if valid else None))
    return result


def counter_segments(rows, metric, until, **scope):
    values = readings(rows, metric, until, **scope)
    segments, issues = [], []
    for (start, before), (end, after) in zip(values, values[1:]):
        if before is None or after is None:
            issues.append('missing_or_conflicting_' + metric)
            continue
        if after < before:
            issues.append('decreased_' + metric)
            continue
        if end > start:
            segments.append((start, end, after - before))
    return segments, issues


def overlap(start, end, left, right):
    return max(0.0, (min(end, right) - max(start, left)).total_seconds())


def change_rate(rows, metric, listing, end, listings, days=30):
    start = end - timedelta(days=days)
    scope = {'shop': listing.get('shop', '').strip().casefold(), 'listings': listings} if metric == 'shop_sales' else {'listing_id': listing['listing_id']}
    if metric == 'shop_sales' and not scope['shop']:
        return None
    segments, _ = counter_segments(rows, metric, end, **scope)
    weighted, covered = 0.0, 0.0
    for left, right, value in segments:
        seconds = overlap(start, end, left, right)
        weighted += value * seconds / (right - left).total_seconds()
        covered += seconds
    # Do not infer a current rate from a series ending long ago or at unknown.
    latest = readings(rows, metric, end, **scope)
    if not latest or latest[-1][1] is None or (end - latest[-1][0]).days > 7:
        return None
    return weighted / (covered / DAY) if covered else None


def features(listing, observations, listings, end):
    result = {'intercept': 1.0}
    windows, _ = purchase_windows(observations, listing['listing_id'], end)
    for unit in ('buyers', 'purchases', 'units'):
        rates = [r['value'] / ((b - a).total_seconds() / DAY) for a, b, r in windows
                 if r.get('unit') == unit and r.get('precision', 'exact') == 'exact' and b >= end - timedelta(days=7)]
        result['message_' + unit] = math.log1p(median(rates)) / 10 if rates else 0.0
        result['message_' + unit + '_missing'] = float(not rates)
    for metric in ('views', 'favorites', 'reviews', 'shop_sales'):
        value = change_rate(observations, metric, listing, end, listings)
        result[metric] = math.log1p(min(value, 1e6)) / 10 if value is not None else 0.0
        result[metric + '_missing'] = float(value is None)
    for metric in ('carts', 'stock', 'price', 'keyword_searches'):
        values = readings(observations, metric, end, listing_id=listing['listing_id'])
        value = values[-1][1] if values and (end - values[-1][0]).days <= 7 else None
        result[metric] = math.log1p(min(value, 1e9)) / 20 if value is not None else 0.0
        result[metric + '_missing'] = float(value is None)
    stock = readings(observations, 'stock', end, listing_id=listing['listing_id'])
    drop = max(0, stock[-2][1] - stock[-1][1]) if len(stock) >= 2 and stock[-2][1] is not None and stock[-1][1] is not None and (end - stock[-1][0]).days <= 7 else None
    result['stock_drop'] = math.log1p(drop) / 10 if drop is not None else 0.0
    result['stock_drop_missing'] = float(drop is None)
    prices = [r for r in observations if r['listing_id'] == listing['listing_id'] and r['metric'] == 'price' and stamp(r['observed_at']) <= end]
    if prices:
        result['currency:' + max(prices, key=lambda r: stamp(r['observed_at'])).get('currency', '')] = 1.0
    created = date.fromisoformat(listing['created_on']) if listing.get('created_on') else None
    result['age'] = math.log1p(max(0, (end.date() - created).days)) / 10 if created else 0.0
    result['digital'] = float(listing.get('product_type') == 'digital')
    result['physical'] = float(listing.get('product_type') == 'physical')
    result['month_sin'] = math.sin(end.month * math.pi / 6)
    result['month_cos'] = math.cos(end.month * math.pi / 6)
    if listing.get('category'):
        result['category:' + listing['category'].strip().casefold()] = 1.0
    return result


def predict(artifact, values):
    linear = sum(artifact['coefficients'].get(k, 0.0) * v for k, v in values.items())
    return max(0.0, math.expm1(max(0.0, min(linear, math.log1p(1e6)))))


def ridge(samples):
    names = sorted({key for vector, _ in samples for key in vector})
    n = len(names)
    matrix = [[sum(x.get(a, 0) * x.get(b, 0) for x, _ in samples) + (0.01 if a == 'intercept' else 2.0) * (a == b)
               for b in names] + [sum(x.get(a, 0) * y for x, y in samples)] for a in names]
    for i in range(n):
        pivot = max(range(i, n), key=lambda j: abs(matrix[j][i]))
        matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
        scale = matrix[i][i]
        if abs(scale) < 1e-12:
            raise ValueError('Calibration data cannot support this model')
        matrix[i] = [v / scale for v in matrix[i]]
        for j in range(n):
            if j != i:
                factor = matrix[j][i]
                matrix[j] = [a - factor * b for a, b in zip(matrix[j], matrix[i])]
    return {name: matrix[i][-1] for i, name in enumerate(names)}


def train(listings, observations, cases):
    """Held-out shops AND later time. No in-sample accuracy or MAPE on zeros."""
    by_id = {x['listing_id']: x for x in listings}
    if len({x.get('category', '').casefold() for x in listings}) > 20:
        raise ValueError('Calibrate comparable products in at most twenty categories per opportunity')
    if len(cases) < 32:
        raise ValueError('Calibration needs at least 32 completed purchase-count cases across eight identified shops')
    ordered = sorted(cases, key=lambda x: (x['period_end'], x['case_id']))
    shops = {x.get('shop', '').strip().casefold() for x in listings if any(c['listing_id'] == x['listing_id'] for c in cases)}
    # One outcome label per listing/window. Overlaps would overweight repeated orders.
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if a['listing_id'] == b['listing_id'] and a['period_start'] <= b['period_end'] and b['period_start'] <= a['period_end']:
                raise ValueError('Calibration windows must not overlap for the same listing')
    splits = []
    for cutoff in sorted({x['period_start'] for x in ordered}):
        test = [x for x in ordered if x['period_start'] >= cutoff]
        test_shops = {by_id[x['listing_id']].get('shop', '').strip().casefold() for x in test}
        training = [x for x in ordered if x['period_end'] < cutoff and by_id[x['listing_id']].get('shop', '').strip().casefold() not in test_shops]
        if '' not in shops and len(shops) >= 8 and len(training) >= 16 and len(test) >= 8 and len(test_shops) >= 2:
            splits.append((abs(len(test) - len(ordered) * .25), cutoff, training, test, test_shops))
    if not splits:
        raise ValueError('Need 16 earlier training cases and eight later cases from at least two separate held-out shops; eight shops overall')
    _, cutoff, training, test, test_shops = min(splits, key=lambda x: (x[0], x[1]))
    def vector(case):
        end = datetime.combine(date.fromisoformat(case['period_end']) + timedelta(days=1), time(), UTC)
        # Snapshot metadata unknown at the cutoff must not leak future listing age.
        listing = dict(by_id[case['listing_id']])
        if listing.get('created_on') and listing['created_on'] > case['period_start']:
            raise ValueError('Calibration cannot predate the listing')
        # Current price/category metadata is declared static by the operator.
        # Seller totals, external estimates and outcomes are never predictors.
        return features(listing, observations, listings, end - timedelta(microseconds=1))
    def target(case):
        days = (date.fromisoformat(case['period_end']) - date.fromisoformat(case['period_start'])).days + 1
        return case['actual_purchases'] / days
    coefficients = ridge([(vector(c), math.log1p(target(c))) for c in training])
    candidate = {'coefficients': coefficients}
    baseline = median(target(c) for c in training)
    results = [{'case_id': c['case_id'], 'actual_daily': target(c), 'predicted_daily': predict(candidate, vector(c))} for c in test]
    mae = sum(abs(r['predicted_daily'] - r['actual_daily']) for r in results) / len(results)
    baseline_mae = sum(abs(baseline - r['actual_daily']) for r in results) / len(results)
    residual = sorted(abs(r['predicted_daily'] - r['actual_daily']) for r in results)
    report = {'training_cases': len(training), 'test_cases': len(test), 'test_shops': len(test_shops), 'cutoff': cutoff,
              'mae_daily': mae, 'baseline_mae_daily': baseline_mae, 'beats_baseline': mae < baseline_mae,
              'results': results, 'coverage_claim': None, 'label_authenticity': 'operator_attested_not_independently_verified'}
    artifact = {'version': VERSION, 'coefficients': coefficients, 'validation': report,
                'scenario_daily_error': residual[min(len(residual) - 1, int(len(residual) * 0.9))],
                'training_fingerprint': digest({'listings': listings, 'observations': observations, 'calibration': cases}),
                'trained_at': datetime.now(UTC).isoformat()}
    artifact['artifact_id'] = digest(artifact)
    # A candidate remains inspectable but is never used unless it beats the baseline.
    artifact['active'] = report['beats_baseline']
    return artifact


def purchase_windows(observations, listing_id, end):
    groups = defaultdict(list)
    for row in observations:
        if row['listing_id'] == listing_id and row['metric'] == 'purchase_message' and stamp(row['observed_at']) <= end:
            groups[stamp(row['observed_at'])].append(row)
    result, issues = [], []
    newer_unknown = None
    for captured, group in sorted(groups.items(), reverse=True):
        signatures = {(r['value'], r.get('unit', 'unknown'), r.get('precision', 'exact'), r.get('window_hours', 24)) for r in group}
        row = group[0]
        if len(signatures) > 1 or row['value'] is None:
            newer_unknown = max(newer_unknown or captured, captured)
            issues.append('missing_or_conflicting_purchase_message')
            continue
        left = captured - timedelta(hours=row.get('window_hours', 24))
        if newer_unknown and newer_unknown - captured < timedelta(hours=row.get('window_hours', 24)):
            continue
        if any(overlap(left, captured, a, b) for a, b, _ in result):
            issues.append('overlapping_purchase_windows_not_added')
            continue
        result.append((left, captured, row))
    return result, list(dict.fromkeys(issues))


def review_rate(listing, observations, listings, end, config):
    if config.get('review_rate') is not None:
        return config['review_rate'], 'operator_assumption'
    shop = listing.get('shop', '').strip().casefold()
    if not shop:
        return None, 'unknown'
    sales = readings(observations, 'shop_sales', end, shop=shop, listings=listings)
    reviews = readings(observations, 'shop_reviews', end, shop=shop, listings=listings)
    if sales and reviews and sales[-1][0] == reviews[-1][0] and sales[-1][1] and reviews[-1][1] is not None:
        ratio = reviews[-1][1] / sales[-1][1]
        if 0 < ratio <= 1 and (end - sales[-1][0]).days <= 7:
            return ratio, 'shop_lifetime_proxy'
    return None, 'unknown'


def estimate_listing(listing, observations, listings, config, artifact, end):
    identity = listing['listing_id']
    created = datetime.combine(date.fromisoformat(listing['created_on']), time(), UTC) if listing.get('created_on') else end - timedelta(days=30)
    windows, issues = purchase_windows(observations, identity, end)
    bins = [{'end': end - timedelta(days=i), 'rates': [], 'anchor': None} for i in range(30)]
    observed = []
    for left, right, row in windows:
        if right <= end - timedelta(days=30):
            continue
        observed.append({**row, 'window_start': left.isoformat(), 'window_end': right.isoformat(), 'scope': 'listing', 'authenticity': 'source_attributed'})
        # Displayed people and units are preserved; no implicit conversion to purchases.
        multiplier = 1 if row.get('unit') == 'purchases' else config.get('purchases_per_buyer') if row.get('unit') == 'buyers' else None
        if multiplier is None or row.get('precision', 'exact') != 'exact':
            issues.append('purchase_unit_or_bound_not_convertible')
            continue
        rate = row['value'] * multiplier / ((right - left).total_seconds() / DAY)
        if row.get('unit') == 'buyers':
            issues.append('buyer_to_purchase_operator_assumption')
        for bucket in bins:
            coverage = overlap(bucket['end'] - timedelta(days=1), bucket['end'], left, right) / DAY
            if coverage:
                bucket['rates'].append(('purchase_message', rate, coverage))
                bucket['anchor'] = True
    ratio, ratio_source = review_rate(listing, observations, listings, end, config)
    segments, review_issues = counter_segments(observations, 'reviews', end, listing_id=identity)
    issues.extend(review_issues)
    if ratio:
        for left, right, count in segments:
            # A uniform assumed lag distribution spreads evidence backwards.
            width = config['review_delay_max'] - config['review_delay_min'] + 1
            for lag in range(config['review_delay_min'], config['review_delay_max'] + 1):
                a, b = left - timedelta(days=lag), right - timedelta(days=lag)
                rate = count / ratio / max((right - left).total_seconds() / DAY, 1e-9)
                for bucket in bins:
                    exposure = overlap(bucket['end'] - timedelta(days=1), bucket['end'], a, b) / DAY / width
                    if exposure:
                        bucket['rates'].append(('reviews', rate, exposure))
    elif segments:
        issues.append('review_rate_unknown')
    view_segments, view_issues = counter_segments(observations, 'views', end, listing_id=identity)
    issues.extend(view_issues)
    if config.get('view_conversion') is not None:
        for left, right, count in view_segments:
            rate = count * config['view_conversion'] / ((right - left).total_seconds() / DAY)
            for bucket in bins:
                exposure = overlap(bucket['end'] - timedelta(days=1), bucket['end'], left, right) / DAY
                if exposure:
                    bucket['rates'].append(('views', rate, exposure))
    trained = artifact and artifact.get('active')
    for bucket in bins:
        predicted = predict(artifact, features(listing, observations, listings, bucket['end'])) if trained else config.get('baseline_daily')
        if predicted is not None:
            predicted *= config['seasonality'][bucket['end'].month - 1]
            bucket['rates'].append(('learned_model' if trained else 'assumed_baseline', predicted, 1.0))
    outputs = {}
    for days in (7, 30):
        selected = bins[:days]
        active_days = overlap(end - timedelta(days=days), end, created, end) / DAY
        daily, coverage, used, dispersion, supported_days = [], 0.0, set(), 0.0, 0.0
        for bucket in selected:
            active_fraction = overlap(bucket['end'] - timedelta(days=1), bucket['end'], created, end) / DAY
            if active_fraction == 0:
                continue
            grouped = defaultdict(list)
            for method, rate, exposure in bucket['rates']:
                grouped[method].append((rate, exposure))
            # Collapse each evidence family before fusion; repetition adds no votes.
            candidates = {key: sum(r * w for r, w in values) / sum(w for _, w in values) for key, values in grouped.items()}
            if not candidates:
                continue
            observed_coverage = min(1.0, sum(w for method, _, w in bucket['rates'] if method != 'assumed_baseline'))
            coverage += observed_coverage * active_fraction
            if 'purchase_message' in candidates:
                anchor_coverage = min(1.0, sum(w for method, _, w in bucket['rates'] if method == 'purchase_message'))
                other = median([v for k, v in candidates.items() if k != 'purchase_message']) if len(candidates) > 1 else candidates['purchase_message']
                rate = anchor_coverage * candidates['purchase_message'] + (1 - anchor_coverage) * other
            else:
                rate = median(candidates.values())
            daily.append(rate * active_fraction)
            supported_days += active_fraction
            bucket['estimate'] = rate
            used.update(candidates)
            dispersion += max(candidates.values()) - min(candidates.values())
        supported = supported_days >= (3 if days == 7 else 14)
        # Baseline-only values need explicit operator assumptions, never automatic defaults.
        estimate = sum(daily) * active_days / supported_days if supported else None
        uncertainty = (0.5 * (1 - coverage / days) + 0.25) if daily else None
        error = (max(1.0, days - coverage, estimate * uncertainty + dispersion * days / max(1, len(daily))) if estimate is not None else None)
        if error is not None and trained:
            error = max(error, artifact['scenario_daily_error'] * days)
        outputs[str(days)] = {'days': days, 'start': (end - timedelta(days=days)).isoformat(), 'end': end.isoformat(), 'estimate': round(estimate, 2) if estimate is not None else None,
            'low': round(max(0, estimate - error), 2) if estimate is not None else None,
            'high': round(estimate + error, 2) if estimate is not None else None,
            'supported_days': round(supported_days, 2), 'active_days': round(active_days, 2), 'coverage_days': round(min(active_days, coverage), 2),
            'extrapolated_days': round(max(0, active_days - supported_days), 2), 'methods': sorted(used), 'unit': 'estimated_purchases',
            'range_type': 'provisional_scenario_envelope', 'status': 'provisional' if supported else 'insufficient_evidence'}
    shop = listing.get('shop', '').strip().casefold()
    shop_segments, shop_issues = counter_segments(observations, 'shop_sales', end, shop=shop, listings=listings) if shop else ([], [])
    issues.extend(shop_issues)
    shop_changes = [{'start': a.isoformat(), 'end': b.isoformat(), 'net_change': v} for a, b, v in shop_segments if b >= end - timedelta(days=30)]
    # Compare rates on the SAME observed interval. Never allocate every shop sale to sampled listings.
    checks = []
    if shop:
        for a, b, value in shop_segments[-5:]:
            days = (b - a).total_seconds() / DAY
            covered = sum(overlap(a, b, x['end'] - timedelta(days=1), x['end']) / DAY for x in bins if 'estimate' in x)
            estimate = sum(x['estimate'] * overlap(a, b, x['end'] - timedelta(days=1), x['end']) / DAY for x in bins if 'estimate' in x) if abs(covered - days) < 0.001 else None
            checks.append({'shop': listing.get('shop'), 'net_shop_change': value, 'days': round(days, 2),
                'estimated_listing_purchases_on_interval': estimate,
                'status': 'review_scope_or_cancellations' if estimate is not None and estimate > value else 'scope_not_directly_comparable'})
    return {'listing_id': identity, 'title': listing['title'], 'shop': listing.get('shop', ''),
        'windows': outputs, 'purchase_evidence': observed, 'shop_changes': shop_changes, 'shop_checks': checks,
        'review_rate': ratio, 'review_rate_basis': ratio_source,
        'issues': sorted(set(issues)), 'features': features(listing, observations, listings, end)}


def run(listings, observations, reviews, patterns, config, artifact=None, calibration=None, at=None, themes=None):
    at = at or datetime.now(UTC)
    calibration = calibration or []
    stale = bool(artifact and artifact.get('training_fingerprint') != digest({'listings': listings, 'observations': observations, 'calibration': calibration}))
    active = artifact if artifact and not stale else None
    results = [estimate_listing(row, observations, listings, config, active, at) for row in listings]
    monthly = [r['windows']['30']['estimate'] for r in results if r['windows']['30']['estimate'] is not None]
    # No market-wide denominator exists: accessibility describes only the sample.
    comparable = [r for r in results if r['windows']['7']['estimate'] is not None]
    shop_values = defaultdict(float)
    for row in comparable:
        if row['shop'].strip():
            shop_values[row['shop'].strip().casefold()] += row['windows']['7']['estimate']
    demand = min(1.0, math.log1p(sum(monthly)) / math.log1p(300)) if monthly else None
    persistence_values = []
    for row in results:
        windows, _ = purchase_windows(observations, row['listing_id'], at)
        current_windows = [(a, b, r) for a, b, r in windows if b >= at - timedelta(days=30)]
        days = {b.date() for _, b, r in current_windows if r['value'] > 0}
        if current_windows:
            persistence_values.append(min(1.0, len(days) / 14))
    persistence = sum(persistence_values) / len(persistence_values) if persistence_values else None
    repeated = [v for v in (themes or {}).values() if v.get('repeated') and v.get('scope') == 'product_or_offer']
    improvement = min(1.0, len(repeated) / 3) if reviews else None
    accessibility = None
    if len(shop_values) >= 3 and sum(shop_values.values()) > 0:
        total = sum(shop_values.values())
        accessibility = 1 - sum((v / total) ** 2 for v in shop_values.values())
    components = {'demand': demand, 'persistence': persistence, 'improvement': improvement, 'accessibility': accessibility}
    complete = all(value is not None for value in components.values())
    score = round(100 * math.prod(components.values()), 1) if complete else None
    return {'version': VERSION, 'as_of': at.isoformat(), 'status': 'provisional' if any(r['windows']['7']['estimate'] is not None for r in results) else 'needs_evidence',
        'trained_model': {'present': bool(artifact), 'active': bool(active and active.get('active')), 'stale': stale,
                          'artifact_id': artifact.get('artifact_id') if artifact else None, 'validation': artifact.get('validation') if artifact else None},
        'listings': results, 'opportunity': {'score': score, 'components': components, 'scope': 'saved_sample',
            'missing': [k for k, v in components.items() if v is None], 'calibrated': False},
        'config': config, 'limits': ['Estimates and scenario ranges are provisional, not verified orders or confidence intervals.',
            'Buyers, units and purchases are different measurements; no automatic unit conversion.',
            'Review delay and conversion assumptions must be validated on seller outcomes.',
            'Default opportunity scales are ranking heuristics, not success probabilities.',
            'Prices do not establish realized revenue, margin or profit.'],
        'factors': ['purchase_messages', 'shop_sales_changes', 'reviews_and_lag', 'views', 'favorites', 'carts',
                    'stock', 'price', 'category', 'product_type', 'listing_age', 'seasonality', 'keyword_demand', 'buyer_feedback'],
        'external_requests': 0}
