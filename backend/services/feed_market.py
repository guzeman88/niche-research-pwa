"""Retain normalized visible Etsy reports for active research candidates."""
from services.product_validation import digest
from datetime import datetime, timezone
import json


def import_observation(con, observation, raw):
    keyword = observation['keyword']
    if not con.execute("SELECT 1 FROM feed_candidates WHERE keyword=? AND tier IN ('active','exploration')", (keyword,)).fetchone():
        raise ValueError('MarketplaceKeywordNotInResearchShortlist')
    sha = digest({'observation': observation, 'raw': raw})
    origin = 'marketplace-packages'; rowid = int(sha[:12], 16)
    if con.execute('SELECT 1 FROM feed_import_records WHERE origin=? AND table_name=? AND source_rowid=? AND sha256=?', (origin, 'package', rowid, sha)).fetchone():
        return {'duplicate': True, 'keyword': keyword}
    con.execute('INSERT INTO feed_import_records VALUES(?,?,?,?,?,?)', (origin, 'package', rowid, sha, json.dumps({'observation': observation, 'raw': raw}), observation['observed_at']))
    run_id = 'marketplace-feed:' + sha
    timestamp = datetime.now(timezone.utc).isoformat()
    con.execute('INSERT INTO evidence_collection_runs(id,source,started_at,completed_at,status,request_json,observation_count) VALUES(?,?,?,?,?,?,2)',
                (run_id, 'etsy_marketplace_insights', timestamp, timestamp, 'completed', json.dumps({'keyword': keyword, 'raw_sha256': sha})))
    for metric, field in [('searches', 'searches'), ('listing_count', 'listings')]:
        con.execute('INSERT OR IGNORE INTO keyword_observations(keyword,source,observed_at,metric,value,unit,metadata_json,geography,period_start,period_end,collection_run_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (keyword, 'etsy_marketplace_insights', raw.get('collected_at') or observation['observed_at'], metric, observation[field], 'searches' if metric == 'searches' else 'listings',
                     json.dumps({'source_note': observation['source_note'], 'rounded_listings': 'approximate' in observation['source_note'], 'package_sha256': sha}),
                     observation['geography'], observation['period_start'], observation['period_end'], run_id))
    return {'duplicate': False, 'keyword': keyword, 'run_id': run_id}
