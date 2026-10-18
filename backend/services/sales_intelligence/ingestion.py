"""Bounded preview/commit and typed source mappings; no inferred reporting windows."""
import csv
import io
import json
import re
from pydantic import ValidationError
from models.sales_intelligence import Reference, Outcome
from . import registry, store

MAX_BYTES = 2_000_000
MAX_ROWS = 2000
ALIASES = {'listing id': 'listing_id', 'product id': 'listing_id', 'etsy id': 'listing_id',
           'monthly sales': 'monthly_sales', 'estimated monthly sales': 'monthly_sales',
           'total sales': 'total_sales', 'weekly sales': 'weekly_sales', '7 days sales': 'weekly_sales',
           'title': 'title', 'shop name': 'shop', 'shop id': 'shop_id', 'price': 'price', 'favorites': 'favorites',
           'listing url': 'url', 'product url': 'url'}


def rows_from(data):
    content = data.get('content', '')
    if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Import at most 2 MB of CSV or JSON')
    if data.get('format', 'json') == 'csv':
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames or len(reader.fieldnames) > 60:
            raise ValueError('CSV needs a bounded header row')
        normalized = [ALIASES.get(h.strip().lower(), h.strip()) for h in reader.fieldnames]
        if len(normalized) != len(set(normalized)):
            raise ValueError('CSV column headings overlap after normalization')
        if any(re.search(r'(password|secret|token|e.?mail|buyer|customer|address)', h or '', re.I) for h in reader.fieldnames):
            raise ValueError('Import listing research only; remove account, credential and buyer columns')
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('CSV row does not match its headings')
            rows.append({ALIASES.get(k.strip().lower(), k.strip()): v for k, v in row.items() if k})
            if len(rows) > MAX_ROWS:
                raise ValueError('Import at most 2,000 rows per batch')
    else:
        try:
            rows = json.loads(content)
        except ValueError as exc:
            raise ValueError('Supply a JSON array or CSV file') from exc
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise ValueError('Supply at most 2,000 JSON rows')
    if not rows:
        raise ValueError('Import contains no rows')
    return rows


def convert(row, data):
    if not isinstance(row, dict):
        raise ValueError('Each reference must be an object')
    if 'metric' in row:
        if row.get('source_id') not in (None, data['source_id']):
            raise ValueError('Row source must match the selected provider')
        value = {**row, 'source_id': data['source_id']}
    else:
        field = data.get('value_column')
        if field not in row:
            raise ValueError('Choose the exact sales column; monthly and lifetime totals are separate')
        identity = str(row.get('listing_id', ''))
        if not identity.isdecimal() and row.get('url'):
            match = re.fullmatch(r'https://(?:www\.)?etsy\.com/listing/(\d+)(?:/[^?#]*)?(?:\?[^#]*)?', row['url'])
            identity = match[1] if match else ''
        raw = str(row[field]).strip().replace(',', '')
        precision = 'lower_bound' if raw.endswith('+') else 'point'
        value = {key: data.get(key) for key in ('basis', 'unit', 'period_start', 'period_end', 'captured_at', 'available_at', 'provider_updated_at') if data.get(key)}
        value.update(source_id=data['source_id'], listing_id=identity, metric='estimated_sales',
                     value=None if raw in ('', 'N/A', '-') else float(raw.rstrip('+')),
                     status='missing' if raw in ('', 'N/A', '-') else 'observed', precision=precision,
                     source_ref=data.get('source_ref', ''), original_label=field)
        if row.get('title'):
            value['metadata'] = {key: row[key] for key in ('title', 'shop', 'shop_id', 'category', 'product_type', 'currency') if row.get(key)}
            value['metadata'].update(listing_id=identity, captured_at=data.get('captured_at'), available_at=data.get('available_at'), source_ref=data.get('source_ref', ''))
    result = Reference.model_validate(value).model_dump(mode='json')
    for item in (result, result.get('metadata') or {}):
        for key in ('period_start', 'period_end', 'captured_at', 'available_at', 'provider_updated_at', 'created_at'):
            if item.get(key):
                item[key] = store.stamp(item[key]).isoformat()
    return result


def preview(data):
    source = registry.source(data.get('source_id'))
    rows = rows_from(data)
    accepted, rejected = [], []
    for index, row in enumerate(rows):
        try:
            accepted.append(convert(row, data))
        except (ValidationError, ValueError, TypeError, OverflowError) as exc:
            message = exc.errors()[0]['msg'] if isinstance(exc, ValidationError) else str(exc)
            rejected.append({'row': index + 1, 'reason': message[:250]})
    fingerprint = store.digest({'source_id': source['id'], 'accepted': accepted, 'rejected': rejected,
                                'content_hash': store.digest(data['content'])})
    return {'fingerprint': fingerprint, 'source_id': source['id'], 'accepted': len(accepted), 'rejected': rejected,
            'sample': accepted[:10], 'can_commit': registry.permission(source['id'], 'storage') and not rejected,
            'blocker': None if registry.permission(source['id'], 'storage') else 'Source storage/reuse evidence has not been recorded',
            '_rows': accepted}


def commit(data):
    result = preview(data)
    if data.get('expected_fingerprint') != result['fingerprint']:
        raise ValueError('Preview changed. Review the import again before committing')
    if not result['can_commit']:
        raise ValueError(result['blocker'] or 'Resolve rejected rows before importing')
    source = result['source_id']
    payload = {'parser_version': 1, 'content': data['content'], 'format': data.get('format', 'json'),
               'mapping': {k: v for k, v in data.items() if k not in ('content', 'expected_fingerprint')}}
    artifact = store.digest({'source_id': source, 'payload': payload})
    inserted = 0
    with store.database(True) as con:
        # Recheck under the writer transaction; a UI flag cannot grant capability.
        if not registry.permission(source, 'storage'):
            raise ValueError('Source access expired before import')
        con.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?)', (artifact, source, store.now().isoformat(), store.encoded(payload)))
        for value in result['_rows']:
            ident = store.digest(value)
            old = value.get('supersedes')
            if old:
                previous = con.execute('SELECT payload FROM observations WHERE id=?', (old,)).fetchone()
                if not previous:
                    raise ValueError('Correction must name an existing original observation')
                before = json.loads(previous[0])
                if any(before[k] != value[k] for k in ('source_id', 'listing_id', 'metric', 'basis', 'unit', 'period_start', 'period_end')):
                    raise ValueError('Correction cannot change the source, listing or reporting cohort')
                if before['available_at'] >= value['available_at']:
                    raise ValueError('Correction must become available after the original')
            cursor = con.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident, source, value['listing_id'], value['metric'], value['basis'], value['unit'], value['available_at'],
                 value['captured_at'], value['period_start'], value['period_end'], artifact, old, store.encoded(value)))
            inserted += cursor.rowcount
            if value.get('metadata'):
                store.add_metadata(con, value['metadata'])
            if old and cursor.rowcount:
                store.set_control(con, 'correction_epoch', store.get_control(con, 'correction_epoch', 0) + 1)
        store.audit(con, 'import', {'artifact': artifact, 'source_id': source, 'inserted': inserted})
    return {'artifact_id': artifact, 'inserted': inserted, 'duplicates': len(result['_rows']) - inserted}


def import_outcomes(data):
    rows = rows_from(data)
    values = [Outcome.model_validate(row).model_dump(mode='json') for row in rows]
    for item in values:
        for key in ('period_start', 'period_end', 'available_at'):
            item[key] = store.stamp(item[key]).isoformat()
    fingerprint = store.digest(values)
    if data.get('expected_fingerprint') != fingerprint:
        return {'fingerprint': fingerprint, 'rows': len(values), 'sample': values[:5], 'committed': False}
    with store.database(True) as con:
        for item in values:
            ident = store.digest(item)
            conflict = con.execute("SELECT id FROM outcomes WHERE listing_id=? AND json_extract(payload,'$.unit')=? AND period_start<? AND period_end>? AND id!=?",
                (item['listing_id'], item['unit'], item['period_end'], item['period_start'], ident)).fetchone()
            if conflict:
                raise ValueError('Actual outcome windows for one listing cannot overlap')
            other_shop = con.execute("SELECT 1 FROM outcomes WHERE listing_id=? AND json_extract(payload,'$.shop_id')!=?", (item['listing_id'], item['shop_id'])).fetchone()
            if other_shop:
                raise ValueError('A listing cannot change canonical shop IDs in outcome records')
            con.execute('INSERT OR IGNORE INTO outcomes VALUES(?,?,?,?,?,?)',
                        (ident, item['listing_id'], item['shop'], item['period_start'], item['period_end'], store.encoded(item)))
        store.audit(con, 'outcomes', {'rows': len(values), 'fingerprint': fingerprint})
    return {'fingerprint': fingerprint, 'rows': len(values), 'committed': True}
