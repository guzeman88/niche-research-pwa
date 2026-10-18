"""Incremental private catalog discovery. Never infer purchases from popularity."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3

from models.selling_products import Listing, Observation, Packet
from services import product_validation as ledger, selling_products as selling

UTC = timezone.utc
BATCH = 5000


def now():
    return datetime.now(UTC)


def root():
    return ledger.db_path().parent / 'selling-discovery'


def native_root():
    return Path(os.environ.get('APP_KEYWORD_FEED_ROOT') or Path.home() / 'EtGen/keyword-feed').resolve()


def native_database():
    base = native_root()
    metadata = base / 'installation.json'
    if not metadata.is_file():
        return None
    path = Path(json.loads(metadata.read_text(encoding='utf-8'))['database']).resolve()
    if not path.is_relative_to((base / 'data').resolve()) or not path.is_file():
        raise ValueError('Saved catalog installation is unavailable')
    return path


def connect():
    directory = root()
    directory.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(directory / 'discovery.sqlite', timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=FULL')
    con.executescript('''
        CREATE TABLE IF NOT EXISTS candidates(
          listing_id TEXT PRIMARY KEY, title TEXT NOT NULL, keyword TEXT NOT NULL,
          shop TEXT NOT NULL, observed_at TEXT NOT NULL, packet TEXT NOT NULL,
          purchase_at TEXT, purchase_until TEXT, review_at TEXT, favorites REAL,
          checked_at TEXT, check_status TEXT NOT NULL DEFAULT 'not_checked',
          next_check TEXT NOT NULL DEFAULT '', opportunity_id TEXT);
        CREATE INDEX IF NOT EXISTS candidates_order ON candidates(observed_at DESC,listing_id);
        CREATE INDEX IF NOT EXISTS candidates_due ON candidates(next_check,observed_at DESC);
        CREATE INDEX IF NOT EXISTS candidates_purchase ON candidates(purchase_at DESC);
        CREATE INDEX IF NOT EXISTS candidates_watchlist ON candidates(opportunity_id) WHERE opportunity_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS control(name TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,started_at TEXT NOT NULL,
          completed_at TEXT,status TEXT NOT NULL,scanned INTEGER NOT NULL DEFAULT 0,
          skipped INTEGER NOT NULL DEFAULT 0,requests INTEGER NOT NULL DEFAULT 0);
    ''')
    return con


def approval():
    """Operator-maintained proof, outside Git. A key or a UI toggle is not proof."""
    path = root() / 'etsy-authorization.json'
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        expires = datetime.fromisoformat(value['expires_at'].replace('Z', '+00:00'))
        issued = datetime.fromisoformat(value['issued_at'].replace('Z', '+00:00'))
        scopes = value['scopes']
        allowed = {'listing_api', 'listing_pages', 'shop_api', 'listing_reviews'}
        if (value.get('issuer') != 'Etsy' or len(value.get('reference', '')) < 10
                or expires.tzinfo is None or issued.tzinfo is None
                or not issued <= now() < expires or not isinstance(scopes, list)
                or not scopes or not set(scopes) <= allowed):
            raise ValueError('Unverified authorization')
        return {'status': 'recorded', 'scopes': scopes, 'expires_at': expires.isoformat()}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'authorization_unverified', 'scopes': [], 'expires_at': None}


def _time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Source timestamps need a timezone')
    return parsed.astimezone(UTC)


def _signals(packet):
    reports = _purchase_reports(packet)
    positive = [v['observed_at'] for v in reports]
    reviews = [v['reviewed_on'] + 'T00:00:00+00:00' for v in packet['reviews']]
    favorites = [v for v in packet['observations'] if v['metric'] == 'favorites']
    favorite = max(favorites, key=lambda v: v['observed_at'])['value'] if favorites else None
    expiry = [(_time(v['observed_at']) + timedelta(hours=min(v['window_hours'], 24))).isoformat()
              for v in reports]
    return max(positive, default=None), max(expiry, default=None), max(reviews, default=None), favorite


def _purchase_reports(packet):
    from services.sales_model import purchase_windows
    windows, _ = purchase_windows(packet['observations'], packet['listings'][0]['listing_id'], now())
    return [value for _, _, value in windows if value['value'] is not None and value['value'] > 0
            and value['source'] == 'etsy_public' and value['unit'] in ('buyers', 'purchases')]


def _merge(before, incoming):
    listings = {v['listing_id']: v for v in before['listings']}
    for value in incoming['listings']:
        previous = listings.get(value['listing_id'])
        # A sparse search snapshot must not erase richer API metadata/images.
        if previous and previous['source'] == 'etsy_public' and value['source'] == 'saved_research':
            continue
        listings[value['listing_id']] = value
    observations = {ledger.digest(selling.identity('observations', v)): v
                    for v in before['observations'] + incoming['observations']}
    # Feed is a bounded working index. Originals remain in the source catalog;
    # promoted private evidence is revisioned and is never removed by refresh.
    groups = {}
    for value in observations.values():
        groups.setdefault((value['metric'], value['source']), []).append(value)
    kept = []
    for (metric, _), values in groups.items():
        kept.extend(sorted(values, key=lambda v: v['observed_at'], reverse=True)[:30 if metric == 'purchase_message' else 2])
    reviews = {v['review_id']: v for v in before['reviews'] + incoming['reviews']}
    return Packet(listings=list(listings.values()), observations=kept,
                  reviews=sorted(reviews.values(), key=lambda v: v['reviewed_on'], reverse=True)[:50]).model_dump(mode='json')


def _upsert(con, packet, keyword, observed_at):
    listing = packet['listings'][0]
    identity = listing['listing_id']
    old = con.execute('SELECT * FROM candidates WHERE listing_id=?', (identity,)).fetchone()
    if old:
        # An older source observation cannot roll back current listing metadata.
        previous = json.loads(old['packet'])
        if _time(observed_at) < _time(old['observed_at']):
            packet['listings'] = previous['listings']
            keyword, observed_at = old['keyword'], old['observed_at']
        packet = _merge(previous, packet)
    purchase, expiry, review, favorite = _signals(packet)
    listing = packet['listings'][0]
    con.execute('''INSERT INTO candidates(listing_id,title,keyword,shop,observed_at,packet,purchase_at,purchase_until,review_at,favorites)
      VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(listing_id) DO UPDATE SET
      title=excluded.title,keyword=excluded.keyword,shop=excluded.shop,
      observed_at=excluded.observed_at,packet=excluded.packet,purchase_at=excluded.purchase_at,
      purchase_until=excluded.purchase_until,review_at=excluded.review_at,favorites=excluded.favorites''',
      (identity, listing['title'], keyword, listing['shop'], observed_at, json.dumps(packet), purchase, expiry, review, favorite))


def sync_catalog():
    """Read-only native input, atomic cursor + index commit, bounded catch-up."""
    path = native_database()
    if path is None:
        return {'status': 'catalog_unavailable', 'scanned': 0, 'skipped': 0}
    with closing(connect()) as target, closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=15)) as source:
        source.row_factory = sqlite3.Row
        maximum = source.execute('SELECT max(id) FROM keyword_listing_snapshots').fetchone()[0] or 0
        target.execute('BEGIN IMMEDIATE')
        saved = target.execute("SELECT value FROM control WHERE name='catalog_cursor'").fetchone()
        # Start with recent observations; don't spend hours replaying old supply.
        cursor = int(saved[0]) if saved else max(0, maximum - 10000)
        if cursor > maximum:
            raise ValueError('Catalog source moved backwards; inspect its installation before resuming')
        rows = source.execute('SELECT * FROM keyword_listing_snapshots WHERE id>? ORDER BY id LIMIT ?', (cursor, BATCH)).fetchall()
        skipped = 0
        for item in rows:
            row = dict(item)
            try:
                identity = str(row['listing_id'])
                if not identity.isdecimal():
                    raise ValueError('Not an Etsy listing ID')
                if not 3 <= len(row['keyword'].strip()) <= 160:
                    raise ValueError('Invalid buyer keyword')
                ref = f"Saved catalog observation {row['id']} / {row.get('collection_run_id') or 'native collection'}"
                listing = Listing(listing_id=identity, title=row['title'], shop=row.get('shop_name') or '',
                    url=f'https://www.etsy.com/listing/{identity}', source='saved_research', source_ref=ref)
                observed = _time(row['observed_at']).isoformat()
                observations = []
                for field, metric in [('price', 'price'), ('favorites', 'favorites'), ('review_count', 'reviews')]:
                    if row.get(field) is not None:
                        observations.append(Observation(listing_id=identity, metric=metric, value=row[field],
                            observed_at=observed, basis='point_in_time' if metric == 'price' else 'lifetime',
                            currency=(row.get('currency_code') or '') if metric == 'price' else '',
                            source='saved_research', source_ref=ref))
                packet = Packet(listings=[listing], observations=observations).model_dump(mode='json')
                _upsert(target, packet, row['keyword'][:160], observed)
            except (ValueError, TypeError):
                skipped += 1
        cursor = rows[-1]['id'] if rows else cursor
        for name, value in [('catalog_cursor', str(cursor)), ('catalog_max', str(maximum)), ('catalog_synced_at', now().isoformat())]:
            target.execute('INSERT OR REPLACE INTO control VALUES(?,?)', (name, value))
        target.commit()
        return {'status': 'caught_up' if cursor >= maximum else 'catching_up', 'scanned': len(rows),
                'skipped': skipped, 'remaining_observations': maximum - cursor}


def browse(q='', signal='all', page=0, limit=20):
    if signal not in ('all', 'purchase_report', 'review_activity', 'unknown'):
        raise ValueError('Unknown discovery filter')
    at = now()
    purchase_cutoff = at.isoformat()
    review_cutoff = (at - timedelta(days=30)).isoformat()
    conditions, params = [], []
    if q:
        conditions.append("(instr(lower(title),?)>0 OR instr(lower(keyword),?)>0 OR instr(lower(shop),?)>0)")
        params.extend([q.casefold()] * 3)
    purchase_sql = '(purchase_until IS NOT NULL AND purchase_until>?)'
    review_sql = '(review_at IS NOT NULL AND review_at>=?)'
    if signal == 'purchase_report':
        conditions.append(purchase_sql); params.append(purchase_cutoff)
    elif signal == 'review_activity':
        conditions.append(review_sql); params.append(review_cutoff)
    elif signal == 'unknown':
        conditions.append('(purchase_until IS NULL OR purchase_until<=?)'); params.append(purchase_cutoff)
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    with closing(connect()) as con:
        total = con.execute('SELECT count(*) FROM candidates' + where, params).fetchone()[0]
        rows = con.execute('SELECT * FROM candidates' + where + ''' ORDER BY
          CASE WHEN purchase_until>? THEN 0 WHEN review_at>=? THEN 1 ELSE 2 END,
          observed_at DESC, favorites DESC, listing_id LIMIT ? OFFSET ?''',
          [*params, purchase_cutoff, review_cutoff, limit, page * limit]).fetchall()
        controls = dict(con.execute('SELECT name,value FROM control').fetchall())
        last = con.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()
        counts = dict(con.execute('''SELECT count(*) AS "indexed",
          coalesce(sum(purchase_until>?),0) purchase_reports,
          coalesce(sum(review_at>=?),0) review_activity FROM candidates''', (purchase_cutoff, review_cutoff)).fetchone())
    items = []
    for row in rows:
        packet = json.loads(row['packet'])
        reports = _purchase_reports(packet)
        fresh = [v for v in reports if _time(v['observed_at']) + timedelta(hours=min(v['window_hours'], 24)) > at]
        report = max(fresh or reports, key=lambda v: _time(v['observed_at']), default=None)
        current = bool(row['purchase_until'] and _time(row['purchase_until']) > at)
        recent_reviews = bool(row['review_at'] and _time(row['review_at']) >= at - timedelta(days=30))
        listing = packet['listings'][0]
        prices = [v for v in packet['observations'] if v['metric'] == 'price']
        price = max(prices, key=lambda v: v['observed_at']) if prices else None
        items.append({**listing, 'keyword': row['keyword'], 'observed_at': row['observed_at'],
            'signal': 'purchase_report' if current else 'review_activity' if recent_reviews else 'unknown',
            'purchase_report': report, 'price': price, 'favorites': row['favorites'],
            'checked_at': row['checked_at'], 'check_status': row['check_status'],
            'opportunity_id': row['opportunity_id'], 'fingerprint': ledger.digest(packet)})
    return {'items': items, 'total': total, 'page': page, 'limit': limit, 'counts': counts,
            'catalog': controls, 'last_run': dict(last) if last else None, 'access': approval(),
            'collection_owner': 'etgen_backend', 'paid_providers': False,
            'sales_limit': 'Purchase reports are source-attributed rolling-window messages, not verified transactions. Reviews and favorites do not establish current purchases.'}


@ledger.single_writer
def investigate(identity, expected):
    """Crash-safe deterministic promotion; repeat clicks never duplicate opportunities."""
    with closing(connect()) as con:
        row = con.execute('SELECT * FROM candidates WHERE listing_id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('Listing is no longer available in discovery')
        packet = json.loads(row['packet'])
        if expected != ledger.digest(packet):
            raise selling.Conflict('Listing evidence changed. Refresh discovery before investigating.')
        project = row['opportunity_id'] or 'discovered-' + identity
        known = ledger.records(project, 'selling_opportunity')
        if not known:
            payload = {'name': row['title'][:140], 'keyword': row['keyword'], 'family': 'other',
                       'notes': 'Discovered from saved catalog. Establish buyer needs and author an original improvement; source sales remain attributed, not independently verified.'}
            from models.selling_products import Opportunity
            payload = Opportunity.model_validate(payload).model_dump(mode='json')
            ledger.put('selling_opportunity', project, payload, 'selling:' + project)
        item = selling.detail(project)
        item = selling.import_packet(project, {'packet': packet, 'expected_fingerprint': item['fingerprint']})['opportunity']
        con.execute('UPDATE candidates SET opportunity_id=? WHERE listing_id=?', (project, identity))
        con.commit()
        return item


@ledger.single_writer
def sync_watchlist():
    """Feed updates append evidence; authored briefs become stale through existing hashes."""
    with closing(connect()) as con:
        rows = con.execute('SELECT listing_id,packet,opportunity_id FROM candidates INDEXED BY candidates_watchlist WHERE opportunity_id IS NOT NULL').fetchall()
    synced = 0
    for row in rows:
        item = selling.detail(row['opportunity_id'])
        selling.import_packet(item['id'], {'packet': json.loads(row['packet']), 'expected_fingerprint': item['fingerprint']})
        synced += 1
    return synced
