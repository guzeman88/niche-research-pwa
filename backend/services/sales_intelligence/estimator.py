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
MAX_TRACKED = 600
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
                old = con.execute('SELECT * FROM estimator_tracking WHERE pinned=0 ORDER BY added_at LIMIT 1').fetchone()
                if not old:
                    raise ValueError('The 600-product tracking panel is full of pinned products')
                from services import selling_collection as cache
                with cache.database() as archive:
                    archive.execute('INSERT OR REPLACE INTO retired VALUES(?,?,?)',(old['listing_id'],store.now().isoformat(),store.encoded(dict(old))))
                con.execute('DELETE FROM estimator_tracking WHERE listing_id=? AND pinned=0',(old['listing_id'],))
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
        existing = {r[0] for r in target.execute(f'SELECT listing_id FROM candidates WHERE listing_id IN ({marks})', ids)}
        # A review can identify a product before its public details are known.
        # The placeholder is transient and cannot be saved without a listing API
        # refresh. It is never used as a product title in estimation evidence.
        from models.selling_products import Listing, Packet
        with store.database() as con:
            for identity in ids:
                if identity in existing:
                    continue
                check = store.get_control(con, 'estimator_check:'+identity, {})
                if check.get('next_check') and store.stamp(check['next_check'])>store.stamp(at):
                    continue
                evidence = con.execute('SELECT payload FROM estimator_evidence WHERE listing_id=? ORDER BY captured_at DESC LIMIT 1', (identity,)).fetchone()
                if not evidence:
                    continue
                item = json.loads(evidence[0])
                packet = Packet(listings=[Listing(listing_id=identity, title='Listing '+identity,
                    shop=item['listing']['shop'], source='etsy_public', source_ref=item['listing']['source_ref'])]).model_dump(mode='json')
                candidates.append({'listing_id':identity,'packet':store.encoded(packet),'keyword':'',
                                   'next_check':'','opportunity_id':None,'pending_metadata':True})
        with store.database() as con:
            positive = {r[0] for r in con.execute('''SELECT t.listing_id FROM estimator_tracking t JOIN estimator_evidence e
              ON e.id=(SELECT x.id FROM estimator_evidence x WHERE x.listing_id=t.listing_id ORDER BY x.captured_at DESC,x.available_at DESC LIMIT 1)
              WHERE json_extract(e.payload,'$.review_window.complete')=1 AND json_extract(e.payload,'$.review_window.observed_reviews')>0
              AND e.captured_at>=?''', ((store.now()-timedelta(days=7)).isoformat(),))}
        candidates = sorted(candidates, key=lambda r: (r['next_check'], r['listing_id'] not in positive, r['listing_id']))
        chosen += [r for r in candidates if r['listing_id'] not in {c['listing_id'] for c in chosen}][:limit-len(chosen)]
    return chosen


def expand_panel(target):
    """Fill a diverse 200-product working panel, then rotate quiet old members.

    Membership retirement is archived separately; authored pins, all historical
    evidence, estimates and research records remain intact. No catalog-wide scan.
    """
    from services import selling_collection as cache
    with store.database() as con:
        if store.get_control(con,'paused',False):
            return
    stamp = store.now()
    last = cache.control('panel_expanded_at')
    if last and stamp-store.stamp(last)<timedelta(minutes=15):
        return
    current = tracking()
    if len(current)>=200:
        with store.database() as con:
            cold = con.execute('''SELECT t.* FROM estimator_tracking t JOIN estimator_latest e USING(listing_id)
                WHERE t.pinned=0 AND t.added_at<?
                ORDER BY json_extract(e.payload,'$.value') IS NOT NULL,
                  coalesce(json_extract(e.payload,'$.value'),0),t.added_at LIMIT 20''',((stamp-timedelta(days=7)).isoformat(),)).fetchall()
        if cold:
            with cache.database() as archive:
                archive.executemany('INSERT OR REPLACE INTO retired VALUES(?,?,?)',
                                    [(r['listing_id'],stamp.isoformat(),store.encoded(dict(r))) for r in cold])
            with store.database(True) as con:
                con.executemany('DELETE FROM estimator_tracking WHERE listing_id=? AND pinned=0',[(r['listing_id'],) for r in cold])
            current = tracking()
    slots = min(20,max(0,200-len(current)))
    if not slots:
        cache.control('panel_expanded_at',value=stamp.isoformat())
        return
    existing = {r['listing_id'] for r in current}
    with cache.database() as archive:
        excluded = {r[0] for r in archive.execute('SELECT listing_id FROM retired WHERE retired_at>?',((stamp-timedelta(days=30)).isoformat(),))}
    fields='listing_id,shop,favorites,observed_at'
    fresh = target.execute(f'SELECT {fields} FROM candidates ORDER BY observed_at DESC,listing_id LIMIT 1000').fetchall()
    cursor = cache.control('panel_catalog_cursor')
    older=[]
    if cursor:
        older=target.execute(f'SELECT {fields} FROM candidates WHERE observed_at=? AND listing_id>? ORDER BY listing_id LIMIT 1000',
                             (cursor['at'],cursor['id'])).fetchall()
        if len(older)<1000:
            older+=target.execute(f'SELECT {fields} FROM candidates WHERE observed_at<? ORDER BY observed_at DESC,listing_id LIMIT ?',
                                  (cursor['at'],1000-len(older))).fetchall()
    else:
        older=fresh
    if older:
        cache.control('panel_catalog_cursor',value={'at':older[-1]['observed_at'],'id':older[-1]['listing_id']})
    elif cursor:
        cache.control('panel_catalog_cursor',value={'at':fresh[-1]['observed_at'],'id':fresh[-1]['listing_id']} if fresh else {})
    rows = list({r['listing_id']:r for r in [*fresh,*older]}.values())
    popular = sorted(rows,key=lambda r:(-(r['favorites'] or 0),store.digest(r['listing_id'])))[:40]
    mixed = popular[:10]+sorted(rows,key=lambda r:store.digest([stamp.date().isoformat(),r['listing_id']]))
    shops = Counter(r['shop'].strip().casefold() for r in target.execute(
        'SELECT shop FROM candidates WHERE listing_id IN ('+','.join('?' for _ in existing)+')',tuple(existing))) if existing else Counter()
    selected = []
    for row in mixed:
        shop = row['shop'].strip().casefold() or 'unknown:'+row['listing_id']
        if row['listing_id'] in existing or row['listing_id'] in excluded or row['listing_id'] in selected or shops[shop]>=5:
            continue
        selected.append(row['listing_id']); shops[shop]+=1
        if len(selected)>=slots:
            break
    with store.database(True) as con:
        # Recheck membership under the writer lock; do not overwrite user pins.
        remaining = max(0,MAX_TRACKED-con.execute('SELECT count(*) FROM estimator_tracking').fetchone()[0])
        con.executemany('INSERT OR IGNORE INTO estimator_tracking VALUES(?,?,0)',[(i,stamp.isoformat()) for i in selected[:remaining]])
    cache.control('panel_expanded_at',value=stamp.isoformat())


def check_delay(listing_id, status):
    if status not in ('api_updated','purchase_message_observed','purchase_message_unavailable'):
        return 24
    with store.database() as con:
        row = con.execute('SELECT payload FROM estimator_evidence WHERE listing_id=? ORDER BY captured_at DESC LIMIT 1',(listing_id,)).fetchone()
    value = json.loads(row[0]) if row else {}
    if value.get('attributes',{}).get('state') in ('inactive','sold_out','removed','expired','draft'):
        return 168
    window = value.get('review_window') or {}
    if window.get('pending'):
        return .25
    return 6 if window.get('observed_reviews',0)>0 else 24


def record_check(listing_id, status, next_check):
    with store.database(True) as con:
        store.set_control(con,'estimator_check:'+listing_id,{'listing_id':listing_id,'check_status':status,
                          'checked_at':store.now().isoformat(),'next_check':next_check})


def follow_reviewed_products(results, start, end, shop_id, primary_id, parent_listing):
    """Reuse a complete shop response for exact-ID recently reviewed products.

    No invented title, buyer record, API request or shop-total allocation.
    Unknown product details remain empty until the normal listing API refresh.
    """
    from services import selling_discovery as discovery
    groups, seen = {}, set()
    for raw in results:
        if not isinstance(raw, dict):
            return []
        identity = str(raw.get('listing_id', ''))
        timestamp = raw.get('created_timestamp', raw.get('create_timestamp'))
        rating = raw.get('rating')
        if (not identity.isdecimal() or len(identity)>30 or str(raw.get('shop_id', shop_id))!=shop_id
                or isinstance(timestamp, bool) or not isinstance(timestamp, (int,float))
                or isinstance(rating, bool) or not isinstance(rating,int) or not 1<=rating<=5):
            return []
        try:
            from datetime import datetime, timezone
            when = datetime.fromtimestamp(timestamp, timezone.utc)
        except (ValueError, OverflowError, OSError):
            return []
        key = store.digest([identity, timestamp, rating, raw.get('review')])
        if not start < when <= end or key in seen:
            return []
        seen.add(key)
        groups.setdefault(identity, []).append(when.isoformat())
    followed, newly_added = [], 0
    with closing(discovery.connect()) as target:
        ensure_panel(target)
        for identity, times in sorted(groups.items(), key=lambda x: (-len(x[1]), x[0])):
            if identity == primary_id:
                continue
            row = target.execute('SELECT packet,observed_at FROM candidates WHERE listing_id=?', (identity,)).fetchone()
            with store.database(True) as con:
                known = con.execute('SELECT 1 FROM estimator_tracking WHERE listing_id=?', (identity,)).fetchone()
                if not known and newly_added>=20:
                    continue
                if not known and con.execute('SELECT count(*) FROM estimator_tracking').fetchone()[0]>=MAX_TRACKED:
                    continue
                con.execute('INSERT OR IGNORE INTO estimator_tracking VALUES(?,?,0)', (identity,store.now().isoformat()))
                newly_added += int(not bool(known))
                prior = con.execute('SELECT payload FROM estimator_evidence WHERE listing_id=? ORDER BY captured_at DESC LIMIT 1',(identity,)).fetchone()
                attributes = json.loads(prior[0]).get('attributes') if prior else None
            listing = dict(json.loads(row[0])['listings'][0]) if row else {'listing_id':identity,'title':''}
            reference='https://api.etsy.com/v3/application/shops/'+shop_id+'/reviews'
            listing.update(shop=parent_listing['shop'])
            if not row:
                listing.update(source='etsy_public',source_ref=reference)
            window = {'start':start.isoformat(),'end':end.isoformat(),'review_times':sorted(times),
                      'observed_reviews':len(times),'reported_count':len(results),'complete':True,'limit':100,
                      'source_ref':reference,'response_scope':'shop_reviews_matched_by_listing_id',
                      'completeness_basis':'bounded_complete_shop_response_matched_to_known_listing'}
            record_capture({'listings':[listing],'observations':[]}, discovery.now(), window,
                           metadata_at=row['observed_at'] if row else None, pending_details=not bool(row),attributes=attributes)
            followed.append(identity)
    return followed


def record_capture(packet, captured_at, review_window=None, metadata_at=None, pending_details=False, attributes=None):
    """Append allowlisted numeric evidence. No buyer IDs, review text or secrets."""
    captured = store.stamp(captured_at).isoformat()
    listing = packet['listings'][0]
    public_listing = {k: listing.get(k) for k in ('listing_id', 'title', 'shop', 'created_on', 'category', 'product_type', 'source', 'source_ref')}
    allowed = {'reviews', 'views', 'favorites', 'stock', 'price', 'shop_sales', 'shop_reviews'}
    observations = [{k: r.get(k) for k in ('listing_id', 'metric', 'value', 'observed_at', 'basis', 'source', 'source_ref', 'currency', 'precision')}
                    for r in packet['observations'] if r['metric'] in allowed]
    value = {'listing': public_listing, 'observations': observations, 'review_window': review_window, 'captured_at': captured,
             'listing_metadata_captured_at': None if pending_details else store.stamp(metadata_at or captured).isoformat()}
    if attributes:
        value['attributes'] = attributes
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
    base.update(listing=latest['listing'], captured_at=latest['captured_at'], listing_metadata_captured_at=latest.get('listing_metadata_captured_at'))
    if latest.get('attributes'):
        base['listing_attributes'] = latest['attributes']
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
    if latest.get('attributes',{}).get('state') in ('inactive','sold_out','removed','expired','draft'):
        base.update(value=None,status='inactive_listing')
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
        checks = {r['listing_id']:store.get_control(con,'estimator_check:'+r['listing_id'],{}) for r in rows}
    from services import selling_discovery as discovery
    with closing(discovery.connect()) as target:
        source = {row['listing_id']: dict(row) for r in rows for row in target.execute('SELECT listing_id,title,shop,checked_at,check_status,next_check FROM candidates WHERE listing_id=?', (r['listing_id'],))}
    items = []
    for row in rows:
        item = json.loads(row['payload']) if row['payload'] else {'listing_id': row['listing_id'], 'status': 'awaiting_api_evidence', 'value': None}
        if item.get('captured_at') and store.now() - store.stamp(item['captured_at']) > timedelta(days=7):
            item.update(value=None, status='stale_evidence', windows={}, review_scenarios={})
        items.append({**item, 'collection': source.get(row['listing_id']) or checks[row['listing_id']], 'pinned': bool(row['pinned'])})
    summary.update(tracked=len(items), estimated=sum(r['value'] is not None for r in items))
    from services import selling_collection as cache
    return {'items': items, 'summary': summary, 'assumptions': ASSUMPTION, 'panel_limit': MAX_TRACKED,'collection_metrics':cache.metrics(),
            'schedule': 'Backend tracking: normal 15-minute source gate, up to 20 direct products and 40 counted requests per pass. Batched details and cached shop review windows share a 4,000-call rolling daily ceiling with keyword research. Active review products are eligible after six hours, quiet products after 24 hours, partial review jobs after 15 minutes, and inactive products after seven days. The rotating panel targets 200 products, with up to 600 including user pins and review-led discoveries.'}
