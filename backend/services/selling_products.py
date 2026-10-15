"""Five research methods over private, revisioned evidence. No external collection."""
import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

from pydantic import ValidationError
from models.selling_products import Opportunity, Packet, Brief, Listing, Observation, Review, Pattern
from services import product_validation as ledger
from services.selling_analysis import analyze

KINDS = {'listings': 'selling_listing', 'observations': 'selling_observation',
         'reviews': 'selling_review', 'patterns': 'selling_pattern'}
MAX_BYTES = 2_000_000


class Conflict(ValueError):
    pass


def identity(kind, value):
    if kind in ('listings', 'patterns'):
        return value['listing_id']
    if kind == 'reviews':
        return [value['listing_id'], value['review_id']]
    return [value[key] for key in ('listing_id', 'metric', 'source', 'source_ref', 'basis',
                                   'observed_at', 'period_start', 'period_end', 'keyword', 'geography')]


def record_id(opportunity, kind, value):
    return 'selling:' + opportunity + ':' + kind + ':' + ledger.digest(identity(kind, value))[:32]


def opportunity_records(opportunity_id):
    rows = ledger.records(opportunity_id)
    if not any(row['kind'] == 'selling_opportunity' for row in rows):
        raise ValueError('Selling-product opportunity not found')
    return rows


def fingerprint(rows):
    # Mirror acknowledgements and unrelated validation records do not alter research.
    return ledger.digest(sorted((r['id'], r['fingerprint']) for r in rows if r['kind'].startswith('selling_')))


def evidence(rows):
    return {key: [r['payload'] for r in rows if r['kind'] == kind] for key, kind in KINDS.items()}


def detail(opportunity_id):
    rows = opportunity_records(opportunity_id)
    packet = evidence(rows)
    opportunity = next(r['payload'] for r in rows if r['kind'] == 'selling_opportunity')
    briefs = [r for r in rows if r['kind'] == 'selling_brief']
    research_rows = [r for r in rows if r['kind'] not in ('selling_brief', 'selling_link')]
    current_evidence = fingerprint(research_rows)
    brief = ({**briefs[0]['payload'], 'stale': briefs[0]['payload']['evidence_fingerprint'] != current_evidence}
             if briefs else None)
    return {'id': opportunity_id, **opportunity, 'fingerprint': fingerprint(rows),
            'evidence_fingerprint': current_evidence, 'evidence': packet,
            'analysis': analyze(**packet), 'brief': brief,
            'pending_sync': sum(r['sync_status'] == 'pending' for r in rows),
            'record_count': len(rows), 'revision_count': revision_count(rows)}


def revision_count(rows):
    if not rows:
        return 0
    with closing(ledger.connect()) as con:
        return con.execute('SELECT count(*) FROM revisions WHERE record_id IN (' + ','.join('?' for _ in rows) + ')',
                           [r['id'] for r in rows]).fetchone()[0]


def overview(query='', stage=''):
    items = []
    for row in ledger.records(kind='selling_opportunity'):
        item = detail(row['project_id'])
        if query.casefold() not in ' '.join((item['name'], item['keyword'], item['audience'])).casefold():
            continue
        if stage and item['stage'] != stage:
            continue
        items.append({key: item[key] for key in ('id', 'name', 'keyword', 'family', 'stage', 'audience', 'fingerprint', 'pending_sync')} | {
            'evidence_level': item['analysis']['evidence_level'],
            'listing_count': item['analysis']['listing_count'],
            'selling_shops': item['analysis']['independent_selling_shops'],
            'has_brief': item['brief'] is not None, 'brief_stale': bool(item['brief'] and item['brief']['stale'])})
    order = {'seller_reported_sales': 0, 'estimated_recent_sales': 1, 'recent_reviews': 2,
             'historical_estimates': 3, 'interest_only': 4, 'needs_evidence': 5}
    items.sort(key=lambda item: (order[item['evidence_level']], -item['selling_shops'], item['name'].casefold()))
    return {'items': items, 'external_collection': False, 'paid_providers': False,
            'methods': ['bestsellers', 'momentum', 'reviews', 'keywords', 'patterns'],
            'data_access': 'Saved research and permitted imports. Expanded automated Etsy analytics authorization is unverified.'}


@ledger.single_writer
def save_opportunity(data, opportunity_id=None, expected=None):
    payload = Opportunity.model_validate(data).model_dump(mode='json')
    if opportunity_id:
        rows = opportunity_records(opportunity_id)
        if expected != fingerprint(rows):
            raise Conflict('This opportunity changed. Refresh before saving your edits.')
    else:
        opportunity_id = uuid.uuid4().hex
    ledger.put('selling_opportunity', opportunity_id, payload, 'selling:' + opportunity_id)
    return detail(opportunity_id)


def parse_import(data):
    content = data.get('content', '')
    if not isinstance(content, str) or len(content.encode()) > MAX_BYTES:
        raise ValueError('Import a text file no larger than 2 MB')
    if data.get('format') == 'json':
        try:
            raw = json.loads(content)
        except ValueError:
            raise ValueError('The JSON file is incomplete or invalid') from None
        if isinstance(raw, dict) and 'evidence' in raw:
            supplied = raw.get('checksum')
            if not supplied or ledger.digest({k: v for k, v in raw.items() if k != 'checksum'}) != supplied:
                raise ValueError('The exported evidence checksum does not match')
            raw = raw['evidence']
        return Packet.model_validate(raw).model_dump(mode='json')
    if data.get('format') != 'csv':
        raise ValueError('Choose JSON or CSV')
    dataset = data.get('dataset', 'listings')
    models = {'listings': Listing, 'observations': Observation, 'reviews': Review, 'patterns': Pattern}
    if dataset not in models:
        raise ValueError('Choose a supported CSV record type')
    reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError('CSV needs unique column headings')
    rows = []
    aliases = {'product_id': 'listing_id', 'shop_name': 'shop', 'product': 'title', 'name': 'title', 'listing_url': 'url'}
    headings = [aliases.get(key.strip().lower().replace(' ', '_'), key.strip().lower().replace(' ', '_')) for key in reader.fieldnames]
    if len(headings) != len(set(headings)):
        raise ValueError('CSV column headings overlap after normalization')
    for index, raw in enumerate(reader, 2):
        if index > 1001:
            raise ValueError('Import at most 1,000 CSV rows at a time')
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError(f'CSV row {index} does not match its headings')
        values = {aliases.get(key.strip().lower().replace(' ', '_'), key.strip().lower().replace(' ', '_')): value.strip()
                  for key, value in raw.items() if value.strip()}
        for field in ('tags', 'features'):
            if field in values:
                values[field] = [part.strip() for part in values[field].split('|') if part.strip()]
        try:
            rows.append(models[dataset].model_validate(values).model_dump(mode='json'))
        except ValidationError as exc:
            raise ValueError(f'CSV row {index}: ' + exc.errors()[0]['msg']) from None
    return Packet.model_validate({dataset: rows}).model_dump(mode='json')


def prepared(opportunity_id, packet):
    rows = opportunity_records(opportunity_id)
    listing_ids = {row['payload']['listing_id'] for row in rows if row['kind'] == KINDS['listings']}
    listing_ids.update(row['listing_id'] for row in packet['listings'])
    known = {row['id']: row for row in rows}
    writes = {}
    for dataset, kind in KINDS.items():
        for payload in packet[dataset]:
            if payload['listing_id'] not in listing_ids:
                raise ValueError('Add the listing before importing its observations, reviews or design attributes')
            key = record_id(opportunity_id, dataset, payload)
            if key in writes and writes[key][1] != payload:
                raise ValueError('The file has conflicting rows for the same evidence identity')
            writes[key] = (kind, payload)
    added = sum(key not in known for key in writes)
    changed = sum(key in known and known[key]['fingerprint'] != ledger.digest(value[1]) for key, value in writes.items())
    return rows, writes, {'added': added, 'changed': changed, 'duplicates': len(writes) - added - changed,
                          'total': len(writes), 'fingerprint': fingerprint(rows)}


def preview(opportunity_id, data):
    packet = parse_import(data)
    _, _, counts = prepared(opportunity_id, packet)
    return {**counts, 'packet': packet, 'source_authenticity': 'not_independently_verified'}


@ledger.single_writer
def import_packet(opportunity_id, data):
    packet = Packet.model_validate(data['packet']).model_dump(mode='json')
    rows, writes, counts = prepared(opportunity_id, packet)
    if data.get('expected_fingerprint') != fingerprint(rows):
        raise Conflict('Evidence changed after the preview. Preview again before importing.')
    # Validate the whole file before any mutation. Each changed value keeps a revision.
    with closing(ledger.connect()) as con, con:
        con.execute('BEGIN IMMEDIATE')
        for key, (kind, payload) in writes.items():
            ledger.write_record(con, key, kind, opportunity_id, json.dumps(payload, sort_keys=True, allow_nan=False),
                                ledger.digest(payload), ledger.stamp())
    return {'imported': counts, 'opportunity': detail(opportunity_id)}


@ledger.single_writer
def save_brief(opportunity_id, data):
    item = detail(opportunity_id)
    if item['fingerprint'] != data.get('expected_fingerprint'):
        raise Conflict('Evidence changed while you edited the brief. Refresh and review it again.')
    brief = Brief.model_validate(data['brief']).model_dump(mode='json')
    # Authored direction is separate from source titles, reviews and artwork.
    brief.update(evidence_fingerprint=item['evidence_fingerprint'], model=item['analysis']['model'])
    ledger.put('selling_brief', opportunity_id, brief, 'selling:' + opportunity_id + ':brief')
    return detail(opportunity_id)


@ledger.single_writer
def export(opportunity_id):
    item = detail(opportunity_id)
    result = {'schema_version': 1, 'exported_at': ledger.stamp(), 'opportunity': {key: item[key] for key in Opportunity.model_fields},
              'evidence': {'schema_version': 1, **item['evidence']}, 'analysis': item['analysis'],
              'brief': item['brief'], 'fingerprint': item['fingerprint'],
              'records': [{key: r[key] for key in ('id', 'kind', 'fingerprint', 'payload')} for r in opportunity_records(opportunity_id)],
              'can_publish': False, 'source_authenticity': 'not_independently_verified'}
    result['checksum'] = ledger.digest(result)
    return result


def production_intake(opportunity_id):
    item = detail(opportunity_id)
    brief = item['brief']
    if not brief:
        raise ValueError('Save an original improvement brief first')
    if brief['stale']:
        raise Conflict('Evidence changed. Review and save the brief again before production intake.')
    if brief['family'] == 'other':
        raise ValueError('This product family has no production renderer. Export the brief for manual development.')
    family = brief['family']
    return {'name': brief['name'], 'keyword': item['keyword'], 'buyer': brief['buyer'],
            'purpose': brief['purpose'], 'family': family, 'content': [],
            'size': 'provider' if family in ('mug', 'apparel') else '8x10' if family == 'wall_art' else 'letter',
            'palette': 'ink', 'layout': 'classic', 'personalization': '', 'price': None,
            'unit_cost': None, 'delivery': '', 'materials': '', 'category_id': None,
            'rights_note': '', 'tags': [], 'supporting_keywords': [], 'provider': {},
            'research': {'selling_opportunity': opportunity_id, 'evidence_fingerprint': item['evidence_fingerprint'],
                         'status': item['analysis']['evidence_level'], 'qualification_credit': False,
                         'original_direction': brief['original_direction'], 'improvements': brief['improvements']},
            'artwork_id': None, 'concept_method': 'authored', 'artwork_method': 'template', 'image_profile': ''}


@ledger.single_writer
def link_validation(opportunity_id):
    item = detail(opportunity_id)
    project_id = 'selling-validation:' + opportunity_id
    if not ledger.records(project_id, 'project'):
        ledger.put('project', project_id, {'name': item['name'], 'product_type': item['family'],
            'keywords': [item['keyword']], 'created_at': ledger.stamp(),
            'source': 'selling_products', 'selling_opportunity': opportunity_id}, project_id)
    # Do not manufacture demand/relevance/cost evidence from competitor estimates.
    return {'project_id': project_id, 'url': '/validation', 'evidence_transferred_as_validation': False}


def research(keyword):
    """Read preserved listing observations. Never initialize or write a research DB."""
    if not 3 <= len(keyword.strip()) <= 160:
        raise ValueError('Enter a buyer keyword of 3–160 characters')
    from services.research_listing import research_connection
    connection = None
    root = Path(os.environ.get('APP_KEYWORD_FEED_ROOT', Path.home() / 'EtGen/keyword-feed'))
    # The native path comes only from the existing trusted installation, never the browser.
    if (root / 'installation.json').is_file():
        metadata = json.loads((root / 'installation.json').read_text())
        path = Path(metadata['database']).resolve()
        if path.is_relative_to((root / 'data').resolve()) and path.is_file():
            connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=15)
            connection.row_factory = sqlite3.Row
    if connection is None:
        connection = research_connection()
    if connection is None:
        return {'packet': Packet().model_dump(mode='json'), 'status': 'research_unavailable'}
    try:
        rows = connection.execute('SELECT * FROM keyword_listing_snapshots WHERE keyword=? ORDER BY observed_at DESC LIMIT 200',
                                  (' '.join(keyword.casefold().split()),)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        connection.close()
    listings, observations, rejected = {}, [], 0
    for value in rows:
        row = dict(value)
        ref = 'Saved research collection ' + str(row.get('collection_run_id') or row.get('observed_at'))
        try:
            listing = Listing(listing_id=str(row['listing_id']), title=row['title'], shop=row.get('shop_name') or '',
                              url=row.get('url') or '', source='saved_research', source_ref=ref).model_dump(mode='json')
            row_observations = []
            for field, metric in [('review_count', 'reviews'), ('favorites', 'favorites'), ('price', 'price')]:
                if row.get(field) is None:
                    continue
                row_observations.append(Observation(listing_id=listing['listing_id'], metric=metric, value=row[field],
                    observed_at=row['observed_at'], basis='point_in_time' if metric == 'price' else 'lifetime',
                    currency=row.get('currency_code') or '' if metric == 'price' else '',
                    source='saved_research', source_ref=ref).model_dump(mode='json'))
            listings.setdefault(listing['listing_id'], listing)
            observations.extend(row_observations)
        except (ValueError, TypeError):
            rejected += 1
    return {'packet': Packet(listings=list(listings.values()), observations=observations).model_dump(mode='json'),
            'status': 'available' if listings else 'no_matching_saved_listings', 'skipped_rows': rejected,
            'sales_available': False, 'external_requests': 0}
