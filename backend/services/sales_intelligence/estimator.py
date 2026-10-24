"""Automatic evidence bridge into EtGen v1; no provider labels or invented orders.

The review scenario is deliberately uncalibrated. Its time axis is review
activity, with a zero-delay assumption, not an observed purchase period.
"""
from collections import Counter
from contextlib import closing
from datetime import timedelta
import json
from models.selling_products import SalesConfig
from services import sales_model
from . import store

VERSION = 'etgen-catalog-estimator-v1'
PANEL_SIZE = 30
MAX_TRACKED = 60
REVIEW_RATES = {'low_sales': .30, 'central': .10, 'high_sales': .02}
ASSUMPTION = ('Uncalibrated sensitivity scenario: 2%, 10% and 30% review probabilities; '
              'one review per purchase and zero purchase-to-review delay. These are design '
              'assumptions, not measured Etsy conversion rates or confidence bounds.')


def tracking():
    with store.database() as con:
        return [dict(r) for r in con.execute('SELECT * FROM estimator_tracking ORDER BY pinned DESC,added_at,listing_id')]


def ensure_panel(target):
    """Stable small panel from the working discovery index, without scanning it."""
    current = tracking()
    if current:
        return current
    rows = target.execute('SELECT listing_id,shop,favorites FROM candidates ORDER BY observed_at DESC,listing_id LIMIT 1000').fetchall()
    shops, selected = Counter(), []
    active = sorted(rows, key=lambda r: (-(r['favorites'] or 0), store.digest(r['listing_id'])))[:500]
    ordered = active[:15] + sorted(rows, key=lambda r: store.digest(r['listing_id']))
    for row in ordered:
        if row['listing_id'] in selected:
            continue
        shop = row['shop'].strip().casefold() or 'unknown:' + row['listing_id']
        if shops[shop] >= 3:
            continue
        shops[shop] += 1
        selected.append(row['listing_id'])
        if len(selected) == PANEL_SIZE:
            break
    with store.database(True) as con:
        # Another worker or a user may have created a panel during the read.
        if not con.execute('SELECT 1 FROM estimator_tracking LIMIT 1').fetchone():
            con.executemany('INSERT OR IGNORE INTO estimator_tracking VALUES(?,?,0)', [(i, store.now().isoformat()) for i in selected])
    return tracking()


def track(listing_id):
    if not isinstance(listing_id, str) or not listing_id.isdecimal() or len(listing_id) > 30:
        raise ValueError('Use a numeric Etsy listing ID')
    from services import selling_discovery as discovery
    with closing(discovery.connect()) as target:
        if not target.execute('SELECT 1 FROM candidates WHERE listing_id=?', (listing_id,)).fetchone():
            raise ValueError('Find this listing in product discovery before tracking it')
        # Keep the public quota bounded; tracking does not force an immediate call.
        ensure_panel(target)
    with store.database(True) as con:
        if not con.execute('SELECT 1 FROM estimator_tracking WHERE listing_id=?', (listing_id,)).fetchone():
            if con.execute('SELECT count(*) FROM estimator_tracking').fetchone()[0] >= MAX_TRACKED:
                raise ValueError('The 60-product tracking panel is full')
        con.execute('INSERT INTO estimator_tracking VALUES(?,?,1) ON CONFLICT(listing_id) DO UPDATE SET pinned=1', (listing_id, store.now().isoformat()))
    return {'status': 'tracked', 'reason': 'Product added to automatic estimation. It will use the normal permitted API schedule and shared free allowance.'}


def due_rows(target, at, limit=3):
    with store.database() as con:
        paused = store.get_control(con, 'paused', False)
    panel = [] if paused else ensure_panel(target)
    ids = [r['listing_id'] for r in panel]
    # Preserve user-authored opportunity priority, but reserve panel turns.
    chosen = target.execute('SELECT * FROM candidates INDEXED BY candidates_watchlist WHERE opportunity_id IS NOT NULL AND next_check<=? ORDER BY next_check,listing_id LIMIT 1', (at,)).fetchall()
    if ids:
        marks = ','.join('?' for _ in ids)
        candidates = target.execute(f'SELECT * FROM candidates WHERE listing_id IN ({marks}) AND next_check<=? ORDER BY next_check,listing_id', (*ids, at)).fetchall()
        chosen += [r for r in candidates if r['listing_id'] not in {c['listing_id'] for c in chosen}][:limit-len(chosen)]
    return chosen


def record_capture(packet, captured_at, review_window=None):
    """Append allowlisted numeric evidence. No buyer IDs, review text or secrets."""
    captured = store.stamp(captured_at).isoformat()
    listing = packet['listings'][0]
    public_listing = {k: listing.get(k) for k in ('listing_id', 'title', 'shop', 'created_on', 'category', 'product_type', 'source', 'source_ref')}
    allowed = {'reviews', 'views', 'favorites', 'stock', 'price', 'shop_sales', 'shop_reviews'}
    observations = [{k: r.get(k) for k in ('listing_id', 'metric', 'value', 'observed_at', 'basis', 'source', 'source_ref', 'currency', 'precision')}
                    for r in packet['observations'] if r['metric'] in allowed]
    value = {'listing': public_listing, 'observations': observations, 'review_window': review_window, 'captured_at': captured}
    ident = store.digest(value)
    with store.database(True) as con:
        con.execute('INSERT OR IGNORE INTO estimator_evidence VALUES(?,?,?,?,?)', (ident, listing['listing_id'], captured, captured, store.encoded(value)))
    return ident


def calculate(listing_id, as_of=None):
    at = store.stamp(as_of) if as_of else store.now()
    if at > store.now():
        raise ValueError('Estimates cannot use a future cutoff')
    with store.database() as con:
        rows = con.execute('SELECT id,payload FROM estimator_evidence WHERE listing_id=? AND captured_at<=? AND available_at<=? ORDER BY captured_at DESC,available_at DESC LIMIT 160', (listing_id, at.isoformat(), at.isoformat())).fetchall()
    base = {'version': VERSION, 'engine': sales_model.VERSION, 'listing_id': listing_id, 'as_of': at.isoformat(),
            'status': 'awaiting_api_evidence', 'value': None, 'days': 30, 'unit': 'estimated_purchases',
            'windows': {}, 'review_scenarios': {}, 'accuracy': 'unvalidated', 'assumptions': ASSUMPTION,
            'review_rates': REVIEW_RATES, 'training_required': False, 'source_ids': [r['id'] for r in rows]}
    if not rows:
        return base
    history = [json.loads(r['payload']) for r in rows]
    latest = history[0]
    base.update(listing=latest['listing'], captured_at=latest['captured_at'])
    if at - store.stamp(latest['captured_at']) > timedelta(days=7):
        base['status'] = 'stale_evidence'
        return base
    observations = [o for r in history for o in r['observations']]
    listing = latest['listing']
    config = SalesConfig().model_dump(mode='json')
    independent = sales_model.estimate_listing(listing, observations, [listing], config, None, at)
    base.update(windows=independent['windows'], issues=independent['issues'], value=independent['windows']['30']['estimate'],
                review_rate_basis=independent['review_rate_basis'])
    base['status'] = 'provisional_independent_estimate' if base['value'] is not None else 'needs_conversion_evidence'
    window = latest.get('review_window')
    if window:
        base['review_evidence'] = window
        if not window.get('complete'):
            base['issues'].append('review_window_incomplete')
        elif window['review_times']:
            # Use our existing estimator on an explicitly complete review window.
            # Do not turn a rolling 30-day count into a lifetime counter. These
            # local counters start at zero at the documented window boundary.
            captured = store.stamp(window['end'])
            start = store.stamp(window['start'])
            times = [store.stamp(t) for t in window['review_times']]
            review_observations = []
            # Completed daily review counts preserve quiet days; interpolating
            # directly between reviews would spread a late review across weeks.
            for day in range(31):
                when = start + timedelta(days=day)
                review_observations.append({'listing_id': listing_id, 'metric': 'reviews',
                    'value': sum(start < t <= when for t in times), 'observed_at': when.isoformat()})
            # A field captured earlier remains an earlier cutoff; do not move old
            # review windows forward just because the worker has run again.
            scenarios = {}
            for label, rate in REVIEW_RATES.items():
                scenario_config = {**config, 'review_rate': rate, 'review_delay_min': 0, 'review_delay_max': 0, 'assumptions_note': ASSUMPTION}
                scenarios[label] = sales_model.estimate_listing(listing, review_observations, [listing], scenario_config, None, captured)['windows']
            for days in (7, 30):
                key = str(days)
                recent = sum(store.stamp(t) > captured - timedelta(days=days) for t in window['review_times'])
                # No reviews is not evidence of zero purchases.
                central = scenarios['central'][key]['estimate'] if recent else None
                base['review_scenarios'][key] = {'days': days, 'value': central,
                    'low': scenarios['low_sales'][key]['estimate'] if central is not None else None,
                    'high': scenarios['high_sales'][key]['estimate'] if central is not None else None,
                    'review_count': recent, 'period_start': (captured - timedelta(days=days)).isoformat(), 'period_end': captured.isoformat(),
                    'basis': 'review_activity_with_assumed_zero_delay', 'range_type': 'assumption_sensitivity_not_confidence_interval'}
            if base['value'] is None and base['review_scenarios']['30']['value'] is not None:
                base.update(value=base['review_scenarios']['30']['value'], status='uncalibrated_review_scenario')
    return base


def refresh():
    from services import selling_discovery as discovery
    with closing(discovery.connect()) as target:
        panel = ensure_panel(target)
    results = [calculate(r['listing_id']) for r in panel]
    with store.database(True) as con:
        for result in results:
            con.execute('INSERT INTO estimator_latest VALUES(?,?,?) ON CONFLICT(listing_id) DO UPDATE SET as_of=excluded.as_of,payload=excluded.payload', (result['listing_id'], result['as_of'], store.encoded(result)))
            identity = store.digest({'version': VERSION, 'listing_id': result['listing_id'], 'source_ids': result['source_ids'], 'day': result['as_of'][:10]})
            con.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?)', (identity, result['listing_id'], 'automatic_estimate', result['as_of'], store.encoded(result)))
        summary = {'at': store.now().isoformat(), 'tracked': len(panel), 'estimated': sum(r['value'] is not None for r in results),
                   'statuses': dict(Counter(r['status'] for r in results)), 'owner': 'etgen_backend'}
        store.set_control(con, 'estimator', summary)
    return summary


def overview():
    with store.database() as con:
        rows = con.execute('SELECT t.listing_id,t.pinned,e.payload FROM estimator_tracking t LEFT JOIN estimator_latest e ON e.listing_id=t.listing_id ORDER BY t.pinned DESC,t.added_at,t.listing_id').fetchall()
        summary = store.get_control(con, 'estimator', {})
    from services import selling_discovery as discovery
    with closing(discovery.connect()) as target:
        source = {row['listing_id']: dict(row) for r in rows for row in target.execute('SELECT listing_id,title,shop,checked_at,check_status,next_check FROM candidates WHERE listing_id=?', (r['listing_id'],))}
    items = []
    for row in rows:
        item = json.loads(row['payload']) if row['payload'] else {'listing_id': row['listing_id'], 'status': 'awaiting_api_evidence', 'value': None}
        if item.get('captured_at') and store.now() - store.stamp(item['captured_at']) > timedelta(days=7):
            item.update(value=None, status='stale_evidence', windows={}, review_scenarios={})
        items.append({**item, 'collection': source.get(row['listing_id']), 'pinned': bool(row['pinned'])})
    summary.update(tracked=len(items), estimated=sum(r['value'] is not None for r in items))
    return {'items': items, 'summary': summary, 'assumptions': ASSUMPTION, 'panel_limit': MAX_TRACKED,
            'schedule': 'Backend tracking: normal 15-minute source gate, at most three due products per pass; each product rechecked after six hours, within the existing shared free allowance.'}
