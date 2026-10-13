"""Atomic, checksum-idempotent Google imports for the broader research shortlist."""
from datetime import datetime, timezone
import json
import math
from services.product_validation import digest
from services.feed_optimization import record_attempt


def import_package(con, package, audit_attempts=True):
    payload = package.get('payload')
    if not isinstance(payload, dict) or digest(payload) != package.get('sha256') or payload.get('source') != 'google_ads_keyword_planner' or payload.get('schema_version') != 1:
        raise ValueError('InvalidGoogleResearchPackage')
    timestamp = payload['collected_at']
    captured = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    if captured.tzinfo is None or captured > datetime.now(timezone.utc):
        raise ValueError('InvalidGoogleCaptureTime')
    sha = package['sha256']; provider = payload['source']; requested = payload['requested_keywords']
    if not 1 <= len(requested) <= 50 or any(not isinstance(k, str) or len(k) > 100 for k in requested):
        raise ValueError('InvalidGoogleResearchKeywords')
    if con.execute('SELECT 1 FROM feed_google_packages WHERE sha256=?', (sha,)).fetchone():
        return {'duplicate': True, 'requested': len(requested)}
    run_id = 'google-feed:' + sha
    con.execute('INSERT INTO feed_import_records VALUES(?,?,?,?,?,?)', ('google-packages', 'package', int(sha[:12], 16), sha, json.dumps(package, sort_keys=True), timestamp))
    for keyword in requested:
        con.execute('INSERT OR IGNORE INTO seeds VALUES(?,?,?,?)', (keyword, 'discovered', provider, timestamp))
    con.execute('INSERT INTO evidence_collection_runs(id,source,started_at,completed_at,status,request_json,observation_count) VALUES(?,?,?,?,?,?,?)',
                (run_id, provider, timestamp, timestamp, 'completed', json.dumps({'keywords': requested, 'package_sha256': sha}), 0))
    matched = {}; observations = 0; seen_aliases = set()
    for signal in payload.get('signals', []):
        keyword = signal['keyword']; metadata = signal.get('metadata') or {}
        aliases = {keyword, *metadata.get('close_variants', [])}.intersection(requested)
        if not aliases:
            raise ValueError('GoogleResultOutsideRequestedKeywords')
        if aliases.intersection(seen_aliases):
            raise ValueError('OverlappingGoogleVariantGroups')
        seen_aliases.update(aliases)
        # Close variants share the same observation. Persist the returned phrase
        # once; retain alias attribution rather than duplicating its volume.
        con.execute('INSERT OR IGNORE INTO seeds VALUES(?,?,?,?)', (keyword, 'discovered', provider, timestamp))
        numeric = []
        if signal.get('monthly_searches') is not None:
            numeric.append(('monthly_searches', signal['monthly_searches'], 'searches_per_month', metadata.get('period_start'), metadata.get('period_end')))
        for item in metadata.get('observations', []):
            if item.get('value') is not None:
                numeric.append((item['metric'], item['value'], item['unit'], item.get('period_start'), item.get('period_end')))
        for metric, value, unit, start, end in numeric:
            if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError('InvalidGoogleMetric')
            con.execute('INSERT OR IGNORE INTO keyword_observations(keyword,source,observed_at,metric,value,unit,metadata_json,geography,period_start,period_end,collection_run_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (keyword, provider, timestamp, metric, value, unit, json.dumps(metadata), payload.get('geography'), start, end, run_id))
            observations += 1
        for point in signal.get('time_series', []):
            if point.get('value') is None:
                continue
            if not math.isfinite(float(point['value'])) or float(point['value']) < 0:
                raise ValueError('InvalidGoogleTrendPoint')
            con.execute('INSERT OR IGNORE INTO keyword_trend_points(keyword,source,point_at,value,unit,geography,timeframe,collected_at,collection_run_id,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (keyword, provider, point['date'], point['value'], point.get('unit', 'searches'), payload.get('geography'), 'calendar_month', timestamp, run_id, json.dumps(metadata)))
        for alias in aliases:
            matched[alias] = bool(numeric)
    for keyword in requested:
        useful = matched.get(keyword, False); status = 'completed' if useful else 'no_data'
        previous = con.execute('SELECT last_attempt_at FROM provider_keyword_state WHERE provider=? AND keyword=?', (provider, keyword)).fetchone()
        if previous and previous[0] > timestamp:
            continue
        con.execute('INSERT INTO provider_keyword_state VALUES(?,?,?,?,?,?,NULL) ON CONFLICT(provider,keyword) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_success_at=excluded.last_success_at,status=excluded.status,row_count=excluded.row_count,error=NULL',
                    (provider, keyword, timestamp, timestamp, status, int(useful)))
        if audit_attempts:
            record_attempt(con, provider, keyword, status, int(useful), timestamp)
    con.execute('UPDATE evidence_collection_runs SET observation_count=?,status=? WHERE id=?', (observations, 'completed' if observations else 'no_data', run_id))
    con.execute('INSERT INTO feed_google_packages VALUES(?,?)', (sha, timestamp))
    return {'duplicate': False, 'requested': len(requested), 'measured_keywords': sum(matched.values()), 'run_id': run_id}
