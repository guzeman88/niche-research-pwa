"""Read-only native history and frozen features available at a declared cutoff."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import gzip
import io
import json
import math
import sqlite3
from models.sales_intelligence import Metadata
from . import store

VERSION = 'reference-features-v2'
COUNTERS = ('views', 'favorites', 'reviews', 'stock', 'price')
RAW_PENDING_LIMIT = 1000
RAW_RETRY_LIMIT = 25


def sync_catalog(limit=1000, backfill=False):
    from services.selling_discovery import native_database
    path = native_database()
    if not path:
        return {'status': 'catalog_unavailable', 'inserted': 0}
    key = 'history_cursor' if backfill else 'catalog_cursor'
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)) as source, store.database(True) as con:
        source.row_factory = sqlite3.Row
        maximum = source.execute('SELECT coalesce(max(id),0) FROM keyword_listing_snapshots').fetchone()[0]
        cursor = store.get_control(con, key, 0 if backfill else max(0, maximum - 10000))
        if cursor > maximum:
            raise ValueError('Native catalog moved backwards; inspect source installation')
        rows = source.execute('SELECT * FROM keyword_listing_snapshots WHERE id>? ORDER BY id LIMIT ?', (cursor, min(5000, limit))).fetchall()
        inserted, skipped = 0, 0
        for raw in rows:
            item = dict(raw)
            try:
                at = store.stamp(item['observed_at']).isoformat()
                # Availability of a native saved observation is its original capture,
                # not this bridge's import time. Do not retrofit future metadata.
                value = Metadata(listing_id=str(item['listing_id']), title=item.get('title') or '',
                    shop=str(item.get('shop_name') or item.get('shop_id') or ''),
                    shop_id=str(item['shop_id']) if item.get('shop_id') else None, captured_at=store.stamp(at),
                    available_at=store.stamp(at), price=item.get('price'), currency=item.get('currency_code') or '',
                    favorites=item.get('favorites'), reviews=item.get('review_count'),
                    source_ref=f"Native saved observation {item['id']}").model_dump(mode='json')
                for date_key in ('captured_at', 'available_at'):
                    value[date_key] = at
                inserted += store.add_metadata(con, value)
            except (ValueError, TypeError):
                skipped += 1
        cursor = rows[-1]['id'] if rows else cursor
        store.set_control(con, key, cursor)
        result = {'status': 'caught_up' if cursor >= maximum else 'catching_up', 'cursor': cursor,
                  'maximum': maximum, 'inserted': inserted, 'skipped': skipped, 'at': store.now().isoformat()}
        store.set_control(con, 'history' if backfill else 'catalog', result)
        return result


def snapshot(con, listing_id, as_of):
    at = store.stamp(as_of)
    rows = con.execute('SELECT payload FROM metadata WHERE listing_id=? AND available_at<=? AND captured_at<=? ORDER BY captured_at DESC,available_at DESC LIMIT 300',
                       (listing_id, at.isoformat(), at.isoformat())).fetchall()
    if not rows:
        return None
    history = [json.loads(r[0]) for r in rows]
    latest = dict(history[0])
    field_times = {}
    for key in (*COUNTERS, 'created_at', 'currency', 'category', 'product_type', 'shop_id'):
        candidates = [r for r in history if r.get(key) not in (None, '', 'unknown')
                      and (key in ('created_at', 'shop_id') or store.stamp(r['captured_at']) >= at - timedelta(days=7))]
        if candidates:
            latest[key] = candidates[0][key]
            field_times[key] = candidates[0]['captured_at']
        elif key in COUNTERS:
            latest[key] = None
    values = {'intercept': 1.0}
    # No teacher estimate or actual outcome is part of these inference features.
    for key in COUNTERS:
        current = latest.get(key)
        values[key] = math.log1p(current) / 20 if current is not None else 0.0
        values[key + '_missing'] = float(current is None)
        rate = None
        earlier = next((r for r in reversed(history) if r.get(key) is not None
                        and store.stamp(r['captured_at']) >= at - timedelta(days=30)
                        and store.stamp(r['captured_at']) < store.stamp(field_times.get(key, latest['captured_at']))), None)
        if earlier and current is not None and current >= earlier[key] and key not in ('stock', 'price'):
            days = (store.stamp(field_times[key]) - store.stamp(earlier['captured_at'])).total_seconds() / 86400
            rate = (current - earlier[key]) / days if days > 0 else None
        values[key + '_rate'] = math.log1p(rate) / 10 if rate is not None else 0.0
        values[key + '_rate_missing'] = float(rate is None)
    created = store.stamp(latest['created_at']) if latest.get('created_at') else None
    values['age'] = math.log1p(max(0, (at - created).total_seconds() / 86400)) / 10 if created else 0.0
    values['age_missing'] = float(created is None)
    values['digital'] = float(latest.get('product_type') == 'digital')
    values['physical'] = float(latest.get('product_type') == 'physical')
    values['month_sin'] = math.sin(at.month * math.pi / 6)
    values['month_cos'] = math.cos(at.month * math.pi / 6)
    for prefix, value, buckets in [('category', latest.get('category', ''), 16), ('currency', latest.get('currency', ''), 8)]:
        if value:
            values[f'{prefix}_bucket_{int(store.digest(value)[:8], 16) % buckets}'] = 1.0
    values['metadata_age_days'] = min(365, max(0, (at - store.stamp(latest['captured_at'])).total_seconds() / 86400)) / 365
    result = {'version': VERSION, 'listing_id': listing_id, 'as_of': at.isoformat(),
              'metadata': latest, 'field_captured_at': field_times, 'values': values, 'input_hash': store.digest(history)}
    result['fingerprint'] = store.digest(result)
    return result


def _import_saved_listing_response(con, row, *, require_capture_time=False):
    """Return inserted/skipped counts and whether a late capture is still unknown."""
    inserted = skipped = 0
    try:
        quota = json.loads(row['quota_json'] or '{}')
        if not isinstance(quota, dict):
            raise ValueError('Saved API quota metadata must be an object')
        if require_capture_time and not quota.get('captured_at'):
            # A request retried long after dispatch cannot be made available at
            # its original attempt time. Wait for the actual response timestamp.
            return 0, 0, True
        at = store.stamp(quota.get('captured_at') or row['attempted_at'])
        with gzip.GzipFile(fileobj=io.BytesIO(row['response_gzip'])) as compressed:
            blob = compressed.read(8_000_001)
        if len(blob) > 8_000_000:
            raise ValueError('Saved response exceeds decoder budget')
        raw = json.loads(blob)
        if not isinstance(raw, dict):
            raise ValueError('Saved API payload is not a listing object')
        items = raw.get('results', [raw] if 'listing_id' in raw else [])
        if not isinstance(items, list):
            raise ValueError('Saved API results must be a list')
        for item in items[:100]:
            if not isinstance(item, dict) or 'title' not in item or 'price' not in item:
                continue  # Reviews/images are not partial listing metadata.
            try:
                price = item.get('price') or {}
                if not isinstance(price, dict):
                    raise ValueError('Saved listing price must be an object')
                amount, divisor = price.get('amount'), price.get('divisor')
                created = item.get('original_creation_timestamp')
                value = Metadata(listing_id=str(item['listing_id']), title=item.get('title') or '',
                    shop=str(item.get('shop_id') or ''), shop_id=str(item['shop_id']) if item.get('shop_id') else None,
                    captured_at=at, available_at=at,
                    category=str(item.get('taxonomy_id') or ''),
                    product_type={'physical': 'physical', 'download': 'digital'}.get(item.get('listing_type'), 'unknown'),
                    created_at=datetime.fromtimestamp(created, timezone.utc) if isinstance(created, (int, float)) and created > 0 else None,
                    price=amount / divisor if isinstance(amount, (int, float)) and isinstance(divisor, (int, float)) and divisor > 0 else None,
                    currency=price.get('currency_code') or '', views=item.get('views'), favorites=item.get('num_favorers'), stock=item.get('quantity'),
                    source_ref=f"Native saved API response {row['id']}").model_dump(mode='json')
                for date_key in ('captured_at', 'available_at', 'created_at'):
                    if value.get(date_key):
                        value[date_key] = store.stamp(value[date_key]).isoformat()
                inserted += store.add_metadata(con, value)
            except (ValueError, TypeError, KeyError, OverflowError):
                skipped += 1
    except (OSError, EOFError, ValueError, TypeError, KeyError):
        skipped += 1
    return inserted, skipped, False


def sync_raw_catalog(limit=25, backfill=False):
    """Decode saved replies with durable, fair retries for unfinished requests.

    The forward scan and pending-ID queue commit with metadata in one archive
    transaction. Native history stays read-only; no request status is repaired
    or assumed failed here. Every pass scans at most 100 new rows and retries at
    most 25 queued primary keys, including when one request never completes.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError('Saved response limit must be a positive integer')
    limit = min(limit, 100)
    from services.selling_discovery import native_database
    path = native_database()
    if not path:
        return {'status': 'catalog_unavailable', 'inserted': 0}
    key = 'raw_history_cursor' if backfill else 'raw_cursor'
    pending_key = key + ':pending'
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)) as source, store.database(True) as con:
        source.row_factory = sqlite3.Row
        if not source.execute("SELECT 1 FROM sqlite_master WHERE name='feed_etsy_requests'").fetchone():
            return {'status': 'saved_responses_unavailable', 'inserted': 0}
        maximum = source.execute('SELECT coalesce(max(id),0) FROM feed_etsy_requests').fetchone()[0]
        cursor = store.get_control(con, key, 0 if backfill else max(0, maximum - 100))
        if cursor > maximum:
            raise ValueError('Native saved request history moved backwards')
        pending = store.get_control(con, pending_key, [])
        if (not isinstance(pending, list) or len(pending) > RAW_PENDING_LIMIT
                or any(type(ident) is not int or not 0 < ident <= cursor for ident in pending)
                or len(pending) != len(set(pending))):
            raise ValueError('Invalid saved response pending queue; preserve it for inspection')
        columns = 'id,attempted_at,status,quota_json,response_gzip'
        retry_ids = pending[:min(limit, RAW_RETRY_LIMIT)]
        pending = pending[len(retry_ids):]
        inserted = skipped = 0
        missing = missing_capture_time = 0
        for ident in retry_ids:
            row = source.execute(f'SELECT {columns} FROM feed_etsy_requests WHERE id=?', (ident,)).fetchone()
            if row is None:
                missing += 1
                pending.append(ident)
            elif row['status'] == 'in_flight':
                pending.append(ident)
            elif row['status'] == '200' and row['response_gzip']:
                added, rejected, unknown_time = _import_saved_listing_response(con, row, require_capture_time=True)
                inserted += added
                skipped += rejected
                if unknown_time:
                    missing_capture_time += 1
                    pending.append(ident)
            # Explicit terminal failures remain unknown, without product values.
            # A 200 row lacking its body is also not a zero-valued observation.
            elif row['status'] == '200':
                pending.append(ident)
        rows = source.execute(f'SELECT {columns} FROM feed_etsy_requests WHERE id>? ORDER BY id LIMIT ?', (cursor, limit)).fetchall()
        scanned = 0
        capacity_reached = False
        for row in rows:
            if row['status'] == 'in_flight':
                if len(pending) >= RAW_PENDING_LIMIT:
                    # Do not cross a hole unless its retry identity is durable.
                    capacity_reached = True
                    break
                pending.append(row['id'])
            elif row['status'] == '200' and row['response_gzip']:
                added, rejected, _ = _import_saved_listing_response(con, row)
                inserted += added
                skipped += rejected
            cursor = row['id']
            scanned += 1
        store.set_control(con, key, cursor)
        store.set_control(con, pending_key, pending)
        status = ('pending_capacity' if capacity_reached else
                  'catching_up' if cursor < maximum else
                  'waiting_on_saved_responses' if pending else 'caught_up')
        return {'status': status, 'inserted': inserted, 'skipped': skipped, 'cursor': cursor,
                'maximum': maximum, 'scanned': scanned, 'retried': len(retry_ids), 'pending': len(pending),
                'missing_pending': missing, 'pending_without_capture_time': missing_capture_time}


def panel(size=30):
    size = max(1, min(500, size))
    with store.database(True) as con:
        # Deterministic random-like ID hash; shop cap avoids a bestseller-only panel.
        rows = con.execute('SELECT payload FROM metadata_latest ORDER BY listing_id LIMIT 10000').fetchall()
        candidates = {json.loads(r[0])['listing_id']: json.loads(r[0]) for r in rows}
        ordered = sorted(candidates.values(), key=lambda x: store.digest(x['listing_id']))
        selected, shops = [], {}
        for item in ordered:
            shop = item.get('shop_id') or item.get('shop') or 'unknown'
            if shops.get(shop, 0) >= 3:
                continue
            shops[shop] = shops.get(shop, 0) + 1
            selected.append(item['listing_id'])
            if len(selected) >= size:
                break
        result = {'purpose': 'reference', 'listing_ids': selected, 'shop_count': len([s for s in shops if s != 'unknown']),
                  'selection': 'stable_id_hash_with_three_per_shop_cap', 'population': 'bounded_saved_catalog_sample',
                  'created_at': store.now().isoformat(), 'random_population_claim': False}
        ident = store.digest(result)
        con.execute('INSERT INTO panels VALUES(?,?)', (ident, store.encoded(result)))
        return {'id': ident, **result}
