"""Project already verified private-ledger evidence into shared research reads.

Retain ledger lineage and source dates; never claim a new provider request.
"""
import json
from services.product_validation import digest
from services.feed_google import import_package
from services.feed_market import import_observation


def import_validation(con, overview):
    imported = 0
    for project in overview.get('projects', []):
        for record in project.get('records', []):
            kind = record['kind']; row = record['payload']
            if kind not in {'competitors', 'google', 'market'}:
                continue
            sha = digest({'record_id': record['id'], 'fingerprint': record['fingerprint']}); rowid = int(sha[:12], 16)
            origin = 'validation-ledger'
            if con.execute('SELECT 1 FROM feed_import_records WHERE origin=? AND table_name=? AND source_rowid=?', (origin, kind, rowid)).fetchone():
                continue
            con.execute('INSERT INTO feed_import_records VALUES(?,?,?,?,?,?)', (origin, kind, rowid, sha, json.dumps(record), record['updated_at']))
            if kind == 'competitors' and row.get('source') == 'etsy_open_api':
                kw = row['keyword']; timestamp = row['observed_at']
                for listing in row.get('listings', []):
                    con.execute('INSERT OR IGNORE INTO keyword_listing_snapshots(keyword,source,observed_at,listing_id,title,shop_name,price,currency_code,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)',
                                (kw, 'etsy_open_api', timestamp, listing['listing_id'], listing.get('title'), listing.get('shop_id'), listing.get('price'), listing.get('currency'), json.dumps({'origin': origin, 'record_id': record['id'], 'fingerprint': record['fingerprint'], 'relevance_reviewed': row.get('relevance_reviewed', False)})))
                if row.get('listings'):
                    con.execute('INSERT INTO provider_keyword_state VALUES(?,?,?,?,?,?,NULL) ON CONFLICT(provider,keyword) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_success_at=excluded.last_success_at,status=excluded.status,row_count=excluded.row_count WHERE excluded.last_attempt_at>provider_keyword_state.last_attempt_at',
                                ('etsy_open_api', kw, timestamp, timestamp, 'completed', len(row['listings'])))
            elif kind == 'google':
                data = {'schema_version': 1, 'source': 'google_ads_keyword_planner',
                        'collected_at': row['collected_at'], 'geography': row.get('geography'),
                        'signals': row['signals'], 'requested_keywords': project['keywords'],
                        'origin': origin, 'ledger_record_id': record['id'], 'ledger_fingerprint': record['fingerprint']}
                import_package(con, {'payload': data, 'sha256': digest(data)}, audit_attempts=False)
            elif kind == 'market':
                import_observation(con, row, {'collected_at': row['observed_at'], 'origin': origin, 'record_id': record['id'], 'fingerprint': record['fingerprint']})
            imported += 1
    return {'imported_records': imported, 'provider_requests': 0}
