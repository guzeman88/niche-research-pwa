"""Private comparison, pagination, outcomes and retryable promotion into research."""
import csv
from contextlib import closing
import io
import json
import sqlite3
from . import consensus, estimator, features, registry, store, training


def overview(q='', page=0, limit=20):
    with store.database() as con:
        search = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        condition = "m.search_text LIKE ? ESCAPE '\\'"
        base = 'FROM metadata_latest m' + (' WHERE ' + condition if q else '')
        params = (search.lower(),) if q else ()
        total = con.execute('SELECT count(*) ' + base, params).fetchone()[0]
        rows = con.execute('SELECT m.payload ' + base + ' ORDER BY m.captured_at DESC,m.listing_id LIMIT ? OFFSET ?',
                           (*params, limit, page * limit)).fetchall()
        items = [json.loads(r[0]) for r in rows]
    feeds = sum(s['automation'] == 'supported_api_configured' and not s['paused'] for s in registry.sources())
    return {'items': items, 'total': total, 'page': page, 'limit': limit, 'coverage': store.counts(),
            'source_count': len(registry.SEEDS), 'automated_provider_feeds': feeds,
            'status': 'reference_sources_pending_access' if feeds < 2 else 'configured_feeds_need_live_verification'}


def coverage():
    with store.database() as con:
        cohorts = [dict(r) for r in con.execute('SELECT source_id,basis,unit,count(*) readings,count(DISTINCT listing_id) listings,max(captured_at) latest_capture FROM observations GROUP BY source_id,basis,unit')]
        metadata = [dict(r) for r in con.execute("SELECT coalesce(json_extract(payload,'$.product_type'),'unknown') product_type,count(*) listings,sum(json_extract(payload,'$.shop_id') IS NOT NULL) canonical_shops_known FROM metadata_latest INDEXED BY metadata_latest_type_shop GROUP BY product_type")]
        shops = con.execute("SELECT count(DISTINCT json_extract(payload,'$.shop_id')) FROM metadata_latest INDEXED BY metadata_latest_shop").fetchone()[0]
        history = store.get_control(con, 'history', {})
    return {**store.counts(), 'cohorts': cohorts, 'catalog_types': metadata, 'canonical_shops': shops,
        'history': history, 'sample_scope': 'Saved catalog and acquired references, not a representative Etsy market census'}


def opportunities(limit=50):
    """Inspectable provisional demand ranking over a bounded acquired-reference set."""
    from datetime import timedelta
    import math
    at = store.now()
    with store.database() as con:
        candidates = con.execute("SELECT listing_id,max(captured_at) last FROM observations WHERE metric='estimated_sales' GROUP BY listing_id ORDER BY last DESC LIMIT 100").fetchall()
        results = []
        for row in candidates:
            report = consensus.build(con, row['listing_id'])
            eligible = [c for c in report['cohorts'] if c['basis'] == 'period' and c['unit'] == 'purchases'
                and abs((store.stamp(c['period_end']) - store.stamp(c['period_start'])).total_seconds() - 30 * 86400) <= 1
                and store.stamp(c['period_end']) >= at - timedelta(days=7)]
            if not eligible:
                continue
            c = max(eligible, key=lambda x: x['period_end'])
            spread = (c['maximum'] - c['minimum']) / max(1, c['center'])
            factors = {'demand': math.log1p(c['center']), 'method_coverage': min(1, c['group_count'] / 3),
                'agreement': 1 / (1 + spread), 'freshness': max(0, 1 - (at - store.stamp(c['period_end'])).total_seconds() / (7 * 86400))}
            score = factors['demand'] * factors['method_coverage'] * factors['agreement'] * factors['freshness']
            meta = con.execute('SELECT payload FROM metadata_latest WHERE listing_id=?', (row['listing_id'],)).fetchone()
            results.append({'listing_id': row['listing_id'], 'metadata': json.loads(meta[0]) if meta else None,
                'score': score, 'factors': factors, 'center': c['center'], 'groups': c['group_count'],
                'period_start': c['period_start'], 'period_end': c['period_end'], 'consensus_fingerprint': c['fingerprint'],
                'status': 'provider_estimate_hypothesis_not_verified_sales'})
    return {'items': sorted(results, key=lambda x: (-x['score'], x['listing_id']))[:limit],
        'sample_limit': 100, 'basis': '30-day purchases only; recent acquired-reference sample',
        'formula': 'log1p(center) × min(1, method_groups/3) × 1/(1+relative_spread) × freshness',
        'limitations': 'Provisional ranking; no profit, market-share or improvement-quality inference. Missing compatible evidence is excluded.'}


def comparison(listing_id, as_of=None):
    at = store.stamp(as_of).isoformat() if as_of else store.now().isoformat()
    if store.stamp(at) > store.now():
        raise ValueError('Historical comparisons cannot use a future cutoff')
    with store.database() as con:
        report = consensus.build(con, listing_id, at)
        feature = features.snapshot(con, listing_id, at)
        rows = con.execute('SELECT id,payload FROM observations WHERE listing_id=? AND available_at<=? ORDER BY available_at DESC LIMIT 200', (listing_id, at)).fetchall()
        history = [{'id': r['id'], **json.loads(r['payload'])} for r in rows]
    return {'listing_id': listing_id, 'metadata': feature['metadata'] if feature else None, 'automatic_estimate': estimator.calculate(listing_id, at),
            'consensus': report, 'student': training.prediction(listing_id, as_of=at), 'history': history,
            'outcome_model': training.prediction(listing_id, as_of=at, lane='actual_outcome'),
            'independent_model': independent(listing_id, at),
            'actual_sales_accuracy': None}


def independent(listing_id, as_of):
    from services import product_validation as ledger, selling_products as selling, sales_model
    from models.selling_products import SalesConfig
    path = ledger.db_path()
    if not path.is_file():
        return {'status': 'no_saved_opportunity_evidence', 'value': None, 'variants': []}
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        projects = con.execute("SELECT DISTINCT project_id FROM records WHERE kind='selling_listing' AND json_extract(payload,'$.listing_id')=? LIMIT 10", (listing_id,)).fetchall()
        variants = []
        for project in projects:
            raw = con.execute('SELECT kind,payload,updated_at FROM records WHERE project_id=? AND updated_at<=?', (project[0], as_of)).fetchall()
            rows = [{'kind': r['kind'], 'payload': json.loads(r['payload'])} for r in raw]
            packet = selling.evidence(rows)
            config = next((r['payload'] for r in rows if r['kind'] == 'selling_model_config'), SalesConfig().model_dump(mode='json'))
            artifact = next((r['payload'] for r in rows if r['kind'] == 'selling_model_artifact'), None)
            result = sales_model.run(**packet, config=config, artifact=artifact, at=store.stamp(as_of))
            item = next((r for r in result['listings'] if r['listing_id'] == listing_id), None)
            if item:
                variants.append({'opportunity_id': project[0], 'windows': item['windows'], 'issues': item['issues']})
    known = {r['windows']['30']['estimate'] for r in variants if r['windows']['30']['estimate'] is not None}
    return {'status': 'provisional_independent_estimate' if len(known) == 1 else 'conflicting_assumptions' if known else 'needs_evidence',
            'value': next(iter(known)) if len(known) == 1 else None, 'days': 30, 'unit': 'purchases', 'variants': variants}


def investigate(listing_id):
    from services import selling_discovery as discovery, product_validation as ledger
    with closing(discovery.connect()) as con:
        row = con.execute('SELECT packet FROM candidates WHERE listing_id=?', (listing_id,)).fetchone()
        if not row:
            raise ValueError('This historical listing is outside the current discovery index. Add it with a buyer keyword in the opportunity workspace.')
        fingerprint = ledger.digest(json.loads(row[0]))
    result = discovery.investigate(listing_id, fingerprint)
    with store.database() as con:
        reference = consensus.build(con, listing_id)
    if any(registry.permission(r['source_id'], 'export') for c in reference['cohorts'] for r in c['readings']):
        queue_promotion(listing_id, result['id'])
    return {'id': result['id'], 'status': 'opened_opportunity'}


def queue_promotion(listing_id, opportunity_id):
    from services.selling_products import opportunity_records
    opportunity_records(opportunity_id)
    with store.database(True) as con:
        report = consensus.build(con, listing_id)
        rows = [r for c in report['cohorts'] for r in c['readings'] if registry.permission(r['source_id'], 'export')]
        if not rows:
            raise ValueError('No eligible source observations are available for research promotion')
        model_refs = {r['key']: json.loads(r['value']) for r in con.execute("SELECT key,value FROM control WHERE key LIKE 'active:%'")}
        payload = {'listing_id': listing_id, 'observations': rows,
            'consensus_fingerprint': store.digest([c['fingerprint'] for c in report['cohorts']]), 'model_versions': model_refs}
        ident = store.digest({'opportunity_id': opportunity_id, 'payload': payload})
        con.execute('INSERT OR IGNORE INTO outbox VALUES(?,?,?,?)', (ident, opportunity_id, 'pending', store.encoded(payload)))
        return {'id': ident, 'status': 'pending'}


def flush_outbox():
    from models.selling_products import Observation, Packet
    from services import selling_products as selling, product_validation as ledger
    with store.database() as con:
        jobs = con.execute("SELECT * FROM outbox WHERE status='pending' ORDER BY id LIMIT 10").fetchall()
    done = 0
    for job in jobs:
        payload = json.loads(job['payload'])
        observations = []
        for item in payload['observations']:
            if not registry.permission(item['source_id'], 'export'):
                continue
            basis = item['basis']
            if basis == 'provider_monthly':
                continue
            start, end = item['period_start'], item['period_end']
            # Existing ledger uses inclusive dates; only exact UTC day boundaries convert.
            if basis == 'period':
                from datetime import timedelta
                a, b = store.stamp(start), store.stamp(end)
                if any((x.hour, x.minute, x.second, x.microsecond) != (0, 0, 0, 0) for x in (a, b)):
                    continue
                start, end = a.date(), (b - timedelta(days=1)).date()
            observations.append(Observation(listing_id=payload['listing_id'], metric='estimated_sales', value=item['value'],
                unit=item['unit'], basis=basis, observed_at=store.stamp(item['captured_at']), period_start=start, period_end=end,
                source='other', source_ref=f"Sales intelligence {item['source_id']} / {item['id']}", note='Provider estimate; not an actual purchase outcome'))
        if not observations:
            with store.database(True) as con:
                con.execute("UPDATE outbox SET status='blocked_incompatible_or_ineligible' WHERE id=?", (job['id'],))
            continue
        detail = selling.detail(job['opportunity_id'])
        packet = Packet(observations=observations).model_dump(mode='json')
        selling.import_packet(job['opportunity_id'], {'expected_fingerprint': detail['fingerprint'], 'packet': packet})
        context = {key: payload.get(key) for key in ('listing_id', 'consensus_fingerprint', 'model_versions')}
        context['observation_ids'] = [item['id'] for item in payload['observations'] if registry.permission(item['source_id'], 'export')]
        context['objective'] = 'attributed_reference_research_not_actual_sales'
        ledger.put('selling_intelligence_context', job['opportunity_id'], context,
            'selling:' + job['opportunity_id'] + ':intelligence:' + payload['listing_id'])
        with store.database(True) as con:
            con.execute("UPDATE outbox SET status='delivered' WHERE id=?", (job['id'],))
        done += 1
    return {'delivered': done, 'pending_examined': len(jobs)}


def export_csv(listing_id):
    with store.database() as con:
        rows = con.execute('SELECT payload FROM observations WHERE listing_id=? ORDER BY available_at LIMIT 2000', (listing_id,)).fetchall()
    allowed = [json.loads(r[0]) for r in rows if registry.permission(json.loads(r[0])['source_id'], 'export')]
    stream = io.StringIO()
    fields = ['source_id', 'listing_id', 'metric', 'value', 'unit', 'basis', 'period_start', 'period_end', 'captured_at', 'available_at', 'source_ref']
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for item in allowed:
        clean = {key: item.get(key) for key in fields}
        for key, value in clean.items():
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                clean[key] = "'" + value
        writer.writerow(clean)
    return stream.getvalue()
