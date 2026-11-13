"""Experimental allocations anchored to observed public shop-counter intervals.

This lane never replaces the existing review scenarios, trains on provider
estimates, calls a source, or changes collection limits. Polling reads a bounded
materialized report; the existing backend estimate job rebuilds it locally.
"""
from collections import Counter, defaultdict
from datetime import timedelta
from contextlib import closing
import json
import math
import re
import sqlite3
from urllib.parse import urlsplit, unquote

from . import store

VERSION = 'etgen-shop-anchored-v1'
MAX_PRODUCTS = 1200
MAX_CAPTURES = 160
LATEST = 'anchored:latest'
ASSUMPTIONS = (
    'Experimental allocation of observed shop-counter increments over their actual '
    'measurement interval. Counter increments are not verified listing purchases '
    'or units. Review probability, purchase-to-review lag and unseen-product '
    'activity remain assumptions. Ranges describe sensitivity, not calibrated '
    'confidence. Public active-catalog coverage cannot establish a complete '
    'historical or private catalog.'
)
SCHEDULE = ('Rebuilt by the existing EtGen backend estimate job from saved permitted '
            'evidence. No additional provider calls, timers or paid services. '
            'Collection retains the existing shared allowance and source gates.')


def _numeric(value):
    return str(value) if not isinstance(value, bool) and re.fullmatch(r'\d{1,30}', str(value or '')) else None


def _shop_reference(value):
    """Canonical exact source identities; display names are never group keys."""
    try:
        url = urlsplit(str(value or ''))
        if url.scheme != 'https' or url.username or url.password or url.port:
            return None
        host = (url.hostname or '').casefold()
        if host == 'api.etsy.com':
            match = re.fullmatch(r'/v3/application/shops/(\d{1,30})(?:/reviews)?/?', url.path)
            return ('id', match[1]) if match else None
        if host in ('etsy.com', 'www.etsy.com'):
            match = re.fullmatch(r'/shop/([A-Za-z0-9_-]{1,120})/?', unquote(url.path))
            return ('url', 'https://www.etsy.com/shop/' + match[1].casefold()) if match else None
    except (ValueError, TypeError):
        pass
    return None


def _read_history(con, listing_id, at):
    """Indexed, bounded numeric history, without repeated large review arrays."""
    rows = con.execute('''SELECT id,captured_at,available_at,
        json_remove(payload,'$.review_window.review_times','$.attributes.description') payload
        FROM estimator_evidence WHERE listing_id=? AND captured_at<=? AND available_at<=?
        ORDER BY captured_at DESC,available_at DESC,id DESC LIMIT ?''',
        (listing_id, at, at, MAX_CAPTURES)).fetchall()
    result = []
    for row in rows:
        item = json.loads(row['payload'])
        item.update(_id=row['id'], _available_at=row['available_at'])
        result.append(item)
    reviews = con.execute('''SELECT id,available_at,json_extract(payload,'$.review_window') window
        FROM estimator_evidence WHERE listing_id=? AND captured_at<=? AND available_at<=?
        AND json_extract(payload,'$.review_window.complete')=1
        ORDER BY captured_at DESC,available_at DESC,id DESC LIMIT 3''', (listing_id, at, at)).fetchall()
    # Multiple different reviews may share a timestamp. Keep the largest observed
    # multiplicity from overlapping responses, rather than collapsing or summing.
    counts, coverage, review_ids = Counter(), [], []
    for row in reviews:
        window = json.loads(row['window'])
        try:
            start, end = store.stamp(window['start']), store.stamp(window['end'])
            if not start < end <= store.stamp(at):
                continue
            raw_times = window.get('review_times', [])
            if not isinstance(raw_times, list) or len(raw_times) > 10000:
                continue
            normalized = [store.stamp(t) for t in raw_times]
            if any(not start < t <= end for t in normalized):
                continue
            local = Counter(t.isoformat() for t in normalized)
        except (ValueError, TypeError, KeyError):
            continue
        counts |= local
        coverage.append({'start': start.isoformat(), 'end': end.isoformat(), 'complete': True})
        review_ids.append(row['id'])
    return result, [t for t in sorted(counts) for _ in range(counts[t])], coverage, review_ids


def build(con, as_of=None, listing_ids=None, catalog_snapshots=None):
    """Read-only replay; accepts a SQLite snapshot connection for offline QA."""
    from .shop_allocation import allocate
    at = store.stamp(as_of) if as_of else store.now()
    if at > store.now():
        raise ValueError('Allocations cannot use a future cutoff')
    stamp = at.isoformat()
    ids = list(listing_ids) if listing_ids is not None else [r[0] for r in con.execute(
        'SELECT listing_id FROM estimator_tracking ORDER BY pinned DESC,added_at,listing_id LIMIT 600')]
    ids = list(dict.fromkeys(i for i in ids if _numeric(i)))[:MAX_PRODUCTS]
    histories, events, coverages, event_ids, catalog = {}, {}, {}, {}, {}
    def load(identity):
        if identity not in histories:
            histories[identity], events[identity], coverages[identity], event_ids[identity] = _read_history(con, identity, stamp)
    for identity in ids:
        load(identity)
    # Only source-verified same-capture IDs can associate legacy URL counters to
    # numeric shop IDs; never infer identity from a display name.
    url_ids = defaultdict(set)
    for history in histories.values():
        for item in history:
            number = _numeric(item.get('attributes', {}).get('shop_id'))
            if number:
                for reading in item.get('observations', []):
                    ref = _shop_reference(reading.get('source_ref'))
                    if reading.get('metric') == 'shop_sales' and ref and ref[0] == 'url':
                        url_ids[ref[1]].add(number)
    # Public catalog snapshots contain no orders, private/inactive inventory or
    # claim of historical completeness. They may contribute additional identities.
    candidate_shops = {i for values in url_ids.values() for i in values}
    for history in histories.values():
        for item in history:
            number = _numeric(item.get('attributes', {}).get('shop_id'))
            if number:
                candidate_shops.add(number)
            for reading in item.get('observations', []):
                ref = _shop_reference(reading.get('source_ref'))
                if ref and ref[0] == 'id':
                    candidate_shops.add(ref[1])
    if catalog_snapshots is None:
        # Do not initialize or mutate a cache while replaying saved history.
        from services import selling_discovery as discovery
        path = discovery.root() / 'collection.sqlite'
        catalog_snapshots = []
        if path.is_file():
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as cache:
                for shop in sorted(candidate_shops):
                    raw = cache.execute('SELECT payload FROM control WHERE key=?', ('anchored_catalog:' + shop,)).fetchone()
                    if raw:
                        catalog_snapshots.append(json.loads(raw[0]))
    for raw in catalog_snapshots or []:
        if not isinstance(raw, dict) or not _numeric(raw.get('shop_id')):
            continue
        try:
            if store.stamp(raw['captured_at']) > at:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        catalog[str(raw['shop_id'])] = raw
        for identity in list(dict.fromkeys([*raw.get('listing_ids', []), *raw.get('known_listing_ids', [])]))[:100]:
            identity = _numeric(identity)
            if identity and identity not in histories and len(histories) < MAX_PRODUCTS:
                ids.append(identity)
                load(identity)
    groups, unidentified = {}, []
    for identity in ids:
        history = histories[identity]
        latest = history[0] if history else {}
        references, numbers = set(), set()
        for item in history:
            number = _numeric(item.get('attributes', {}).get('shop_id'))
            if number:
                numbers.add(number)
            for reading in item.get('observations', []):
                ref = _shop_reference(reading.get('source_ref'))
                if reading.get('metric') != 'shop_sales' or reading.get('basis') != 'lifetime' or reading.get('source') != 'etsy_public' or not ref:
                    continue
                if ref[0] == 'id':
                    numbers.add(ref[1])
                else:
                    references.add(ref[1])
                    if len(url_ids.get(ref[1], set())) == 1:
                        numbers.update(url_ids[ref[1]])
        # A catalog identity without a direct capture can still appear as an
        # unknown allocation member of its exact numeric parent shop.
        catalog_parents = {shop for shop, raw in catalog.items() if identity in
                           [str(i) for i in [*raw.get('listing_ids', []), *raw.get('known_listing_ids', [])]]}
        numbers.update(catalog_parents)
        key = next(iter(numbers)) if len(numbers) == 1 else next(iter(references)) if not numbers and len(references) == 1 else None
        public = latest.get('listing', {})
        product = {'listing_id': identity, 'title': public.get('title', ''), 'shop': public.get('shop', ''),
            'review_times': events[identity], 'review_coverage': coverages[identity],
            'metadata_at': latest.get('listing_metadata_captured_at'), 'state': latest.get('attributes', {}).get('state'),
            'catalog_seen': bool(catalog_parents)}
        if not key:
            unidentified.append({**product, 'review_times': [], 'review_coverage': [], 'shop_id': None,
                'value': None, 'low': None, 'high': None, 'status': 'shop_identity_unknown_or_conflicting',
                'unit': 'shop_counter_increments', 'window': None, 'validation': 'unvalidated',
                'issues': ['canonical_shop_identity_required']})
            continue
        group = groups.setdefault(key, {'products': [], 'counter_readings': [], 'source_ids': set(), 'shop_label': public.get('shop', '')})
        group['products'].append(product)
        group['source_ids'].update([item['_id'] for item in history] + event_ids[identity])
        for item in history:
            for reading in item.get('observations', []):
                ref = _shop_reference(reading.get('source_ref'))
                if reading.get('metric') != 'shop_sales' or reading.get('basis') != 'lifetime' or reading.get('source') != 'etsy_public' or not ref:
                    continue
                target = ref[1] if ref[0] == 'id' else next(iter(url_ids[ref[1]])) if len(url_ids.get(ref[1], set())) == 1 else ref[1]
                if target != key or reading.get('precision', 'exact') != 'exact':
                    continue
                group['counter_readings'].append({'observed_at': reading['observed_at'], 'value': reading.get('value'),
                    'available_at': item['_available_at'], 'source_id': item['_id']})
    shops, items = [], list(unidentified)
    for key, group in sorted(groups.items()):
        result = allocate(key, group['counter_readings'], group['products'], as_of=at,
                          config={'catalog_complete': False})
        result.update(shop_label=group['shop_label'], source_ids=sorted(group['source_ids']),
                      catalog_context={k: catalog.get(key, {}).get(k) for k in ('captured_at', 'active_count', 'public_complete')})
        result['source_fingerprint'] = store.digest({'version': VERSION, 'ids': result['source_ids'],
            'catalog': result['catalog_context'], 'window': result.get('window')})
        details = {p['listing_id']: p for p in group['products']}
        for p in result['products']:
            source = details[p['listing_id']]
            p.update(title=source['title'], shop=source['shop'], shop_id=key, window=result.get('window'),
                unit='shop_counter_increments', validation='unvalidated', range_type=result['range_type'],
                source_fingerprint=result['source_fingerprint'])
            items.append(p)
        shops.append(result)
    summary = {'at': stamp, 'tracked': len(ids), 'shops': len(shops),
        'anchored_shops': sum(s.get('window') is not None for s in shops),
        'allocated_products': sum(i.get('value') is not None for i in items),
        'unknown_products': sum(i.get('value') is None for i in items),
        'statuses': dict(Counter(i['status'] for i in items)), 'owner': 'etgen_backend'}
    return {'version': VERSION, 'as_of': stamp, 'summary': summary, 'items': items, 'shops': shops,
            'assumptions': ASSUMPTIONS, 'accuracy': 'unvalidated', 'schedule': SCHEDULE,
            'validation': empty_validation()}


def empty_validation():
    return {'status': 'awaiting_compatible_independent_outcomes', 'matched_cases': 0, 'mae': None, 'wape': None,
            'within_five_percent': None, 'actual_sales_accuracy': None,
            'counter_unit': 'unverified', 'holdout': 'No fitted model; future tuning must reserve new shops and later dates.'}


def evaluate_frozen(predictions, outcomes, mapping=None):
    """Exact-window seller-label evaluation, gated by independently verified units.

    Mapping is protected operator configuration, never inferred from the counter
    field name or supplied by an external estimate. There is no activation here.
    """
    report = empty_validation()
    if not isinstance(mapping, dict) or mapping.get('verified') is not True or mapping.get('unit') not in ('units', 'purchases') or not mapping.get('source_ref'):
        report['status'] = 'counter_unit_verification_required'
        return report
    unit = mapping['unit']
    report['counter_unit'] = unit
    labels = defaultdict(list)
    for o in outcomes:
        if o.get('unit') != unit or not o.get('attestation') or not o.get('source_ref') or not _numeric(o.get('shop_id')):
            continue
        actual = o.get('actual')
        if isinstance(actual, bool) or not isinstance(actual, (float, int)) or not math.isfinite(actual) or actual < 0:
            continue
        try:
            key = (o['listing_id'], str(o['shop_id']), store.stamp(o['period_start']).isoformat(), store.stamp(o['period_end']).isoformat())
            labels[key].append(o)
        except (ValueError, KeyError, TypeError):
            continue
    pairs, seen = [], set()
    # First immutable estimate for a listing/window wins, so later recalculation
    # cannot quietly substitute a result after a seller label becomes available.
    for p in sorted(predictions, key=lambda x: x.get('frozen_at', '')):
        window = p.get('window') or {}
        key = (p.get('listing_id'), str(p.get('shop_id')), window.get('start'), window.get('end'))
        if key in seen or len(labels.get(key, [])) != 1 or p.get('value') is None:
            continue
        seen.add(key)
        o = labels[key][0]
        try:
            if not store.stamp(p['frozen_at']) < store.stamp(o['available_at']):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        pairs.append((float(p['value']), float(o['actual'])))
    if not pairs:
        return report
    errors = [abs(pred - actual) for pred, actual in pairs]
    denominator = sum(actual for _, actual in pairs)
    positive = [(pred, actual) for pred, actual in pairs if actual > 0]
    report.update(status='frozen_estimates_evaluated_on_attested_outcomes', matched_cases=len(pairs),
        mae=sum(errors) / len(errors), wape=sum(errors) / denominator if denominator else None,
        positive_cases=len(positive), zero_cases=len(pairs) - len(positive),
        within_five_percent=sum(abs(pred - actual) <= actual * .05 for pred, actual in positive) / len(positive) if positive else None,
        actual_sales_accuracy='limited_to_retained_exact_window_operator_attested_labels')
    return report


def rebuild(as_of=None):
    at = store.stamp(as_of) if as_of else store.now()
    with store.database() as con:
        result = build(con, at.isoformat())
    frozen_at = store.now().isoformat()
    with store.database(True) as con:
        for item in result['items']:
            if item.get('value') is None or not item.get('window'):
                continue
            # Freeze one immutable first estimate per model + exact listing/window.
            key = store.digest({'version': VERSION, 'listing_id': item['listing_id'], 'shop_id': item['shop_id'], 'window': item['window']})
            frozen = {**item, 'version': VERSION, 'as_of': at.isoformat(), 'frozen_at': frozen_at}
            con.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?)',
                        (key, item['listing_id'], 'shop_allocation', at.isoformat(), store.encoded(frozen)))
        # Evaluate only bounded archived predictions and genuine seller outcomes;
        # provider observations never enter this path.
        predictions = [json.loads(r[0]) for r in con.execute("SELECT payload FROM snapshots WHERE kind='shop_allocation' ORDER BY as_of DESC LIMIT 10000")]
        outcomes = [json.loads(r[0]) for r in con.execute('SELECT payload FROM outcomes ORDER BY period_end DESC LIMIT 10000')]
        result['validation'] = evaluate_frozen(predictions, outcomes, store.get_control(con, 'anchored:counter_unit_mapping'))
        store.set_control(con, LATEST, result)
        priorities = {p['listing_id']: {'score': p['score'], 'reason': p['reason']} for shop in result['shops'] for p in shop['priority']}
        store.set_control(con, 'anchored:priority', {'at': at.isoformat(), 'items': priorities})
    return result['summary']


def overview():
    with store.database() as con:
        result = store.get_control(con, LATEST)
    if not result:
        return {'version': VERSION, 'as_of': None, 'summary': {'tracked': 0, 'shops': 0, 'anchored_shops': 0,
            'allocated_products': 0, 'unknown_products': 0, 'status': 'awaiting_backend_calculation'},
            'items': [], 'shops': [], 'assumptions': ASSUMPTIONS, 'accuracy': 'unvalidated',
            'validation': empty_validation(), 'schedule': SCHEDULE}
    # A stale materialized report must not continue looking like a live estimate.
    report_stale = store.now() - store.stamp(result['as_of']) > timedelta(days=7)
    stale_shops = {s['shop_id'] for s in result['shops'] if report_stale or
                   (s.get('window') and store.now()-store.stamp(s['window']['end']) > timedelta(days=7))}
    if report_stale or stale_shops:
        result['summary']['status'] = 'stale_evidence'
        for item in result['items']:
            if report_stale or item.get('shop_id') in stale_shops:
                item.update(value=None, low=None, high=None, window=None, status='stale_evidence')
        for shop in result['shops']:
            if shop['shop_id'] not in stale_shops:
                continue
            shop['status'] = 'stale_evidence'
            shop['window'] = None
            shop['unobserved'] = {'value':None,'low':None,'high':None}
            for item in shop['products']:
                item.update(value=None, low=None, high=None, window=None, status='stale_evidence')
        result['summary']['anchored_shops'] = sum(s.get('window') is not None for s in result['shops'])
        result['summary']['allocated_products'] = sum(i.get('value') is not None for i in result['items'])
        result['summary']['unknown_products'] = sum(i.get('value') is None for i in result['items'])
    # Full source IDs remain in the protected materialization. A polling response
    # returns bounded provenance and its complete fingerprint instead.
    for shop in result['shops']:
        source_ids = shop.pop('source_ids', [])
        shop['source_evidence_count'] = len(source_ids)
        shop['source_ids'] = source_ids[:20]
        shop['source_ids_truncated'] = len(source_ids) > 20
    return result


def priorities():
    """Small persisted scheduling input; no history/model work while selecting."""
    with store.database() as con:
        result = store.get_control(con, 'anchored:priority', {})
    if not result.get('at') or store.now() - store.stamp(result['at']) > timedelta(days=7):
        return {}
    return result.get('items', {})


def listing(listing_id, as_of=None):
    if as_of:
        with store.database() as con:
            rows = con.execute("SELECT payload FROM snapshots WHERE listing_id=? AND kind='shop_allocation' AND as_of<=? ORDER BY as_of DESC LIMIT 1",
                               (listing_id, store.stamp(as_of).isoformat())).fetchone()
        return json.loads(rows[0]) if rows else None
    return next((i for i in overview()['items'] if i['listing_id'] == listing_id), None)
