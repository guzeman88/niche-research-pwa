"""Conservative collection priorities, cooldowns and measured coverage.

Priority is an explicit research heuristic, never a profitability prediction.
All seeds/history survive; only the active work allocation changes.
"""
from datetime import datetime, timedelta, timezone
import json
import os
import re

PROVIDERS = {"etsy_open_api": 7, "google_suggest": 14, "google_ads_keyword_planner": 28}
PRODUCTS = re.compile(r"\b(mugs?|shirts?|tees?|stickers?|decals?|prints?|posters?|ornaments?|totes?|bags?|signs?|hangers?|decor|notebooks?|journals?|tumblers?|microphones?|accessories|invitations?|templates?|planners?|gifts?)\b")
ARTIFICIAL = re.compile(r"micro-business|micro-identity|micro-mugs?|micro-tees?|microbrewed print|identity apparel")


def schema(con):
    con.executescript("""
      CREATE TABLE IF NOT EXISTS feed_candidates(
        keyword TEXT PRIMARY KEY, priority INTEGER NOT NULL, tier TEXT NOT NULL,
        reasons TEXT NOT NULL, cluster TEXT NOT NULL, updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS feed_provider_cooldowns(
        provider TEXT NOT NULL, keyword TEXT NOT NULL, empty_streak INTEGER NOT NULL,
        failure_streak INTEGER NOT NULL, next_due TEXT NOT NULL,
        PRIMARY KEY(provider,keyword));
      CREATE TABLE IF NOT EXISTS feed_provider_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL, keyword TEXT NOT NULL,
        attempted_at TEXT NOT NULL, status TEXT NOT NULL, row_count INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS feed_attempts_time ON feed_provider_attempts(attempted_at);
      CREATE TABLE IF NOT EXISTS feed_import_checkpoints(
        origin TEXT NOT NULL, table_name TEXT NOT NULL, last_rowid INTEGER NOT NULL,
        anchor_sha256 TEXT, PRIMARY KEY(origin,table_name));
      CREATE TABLE IF NOT EXISTS feed_import_records(
        origin TEXT NOT NULL, table_name TEXT NOT NULL, source_rowid INTEGER NOT NULL,
        sha256 TEXT NOT NULL, payload TEXT NOT NULL, imported_at TEXT NOT NULL,
        PRIMARY KEY(origin,table_name,source_rowid));
      CREATE TABLE IF NOT EXISTS feed_google_packages(sha256 TEXT PRIMARY KEY, imported_at TEXT NOT NULL);
    """)


def utc(value=None):
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def record_attempt(con, provider, keyword, status, rows, timestamp):
    old = con.execute('SELECT * FROM feed_provider_cooldowns WHERE provider=? AND keyword=?', (provider, keyword)).fetchone()
    old_empty = old['empty_streak'] if old else 0
    empty = old_empty + 1 if status == 'no_data' else 0 if status in {'completed', 'partial', 'unchanged'} and rows else old_empty
    failed = (old['failure_streak'] if old else 0) + 1 if status not in {'completed', 'no_data', 'unchanged', 'partial'} else 0
    days = min(90, max(PROVIDERS.get(provider, 7), 7 * 2 ** min(empty - 1, 4))) if empty else PROVIDERS.get(provider, 14)
    delay = timedelta(hours=min(24, 2 ** min(failed, 5))) if failed else timedelta(days=days)
    con.execute('INSERT INTO feed_provider_attempts(provider,keyword,attempted_at,status,row_count) VALUES(?,?,?,?,?)',
                (provider, keyword, timestamp, status, max(0, int(rows))))
    con.execute('INSERT OR REPLACE INTO feed_provider_cooldowns VALUES(?,?,?,?,?)',
                (provider, keyword, empty, failed, (utc(timestamp) + delay).isoformat()))


def provider_due(con, provider, keyword, at=None):
    at = at or datetime.now(timezone.utc)
    if not provider_available(con, provider, at):
        return False
    if provider == 'google_suggest':
        # The independent collector's immutable observations are imported,
        # while its mutable provider-state table is deliberately not copied.
        observed = con.execute("SELECT max(observed_at) FROM keyword_suggestions WHERE parent_keyword=? AND source='google_suggest'", (keyword,)).fetchone()[0]
        if observed and utc(observed) <= at < utc(observed) + timedelta(days=PROVIDERS[provider]):
            return False
    row = con.execute('SELECT next_due FROM feed_provider_cooldowns WHERE provider=? AND keyword=?', (provider, keyword)).fetchone()
    if row:
        return utc(row['next_due']) <= at
    # Respect provider history from before cooldown installation too.
    old = con.execute('SELECT last_attempt_at,status FROM provider_keyword_state WHERE provider=? AND keyword=?', (provider, keyword)).fetchone()
    if not old:
        return True
    delay = timedelta(hours=2) if old['status'] == 'failed' else timedelta(days=PROVIDERS.get(provider, 14))
    return utc(old['last_attempt_at']) + delay <= at


def provider_available(con, provider, at=None):
    at = at or datetime.now(timezone.utc)
    row = con.execute('SELECT next_due FROM feed_provider_cooldowns WHERE provider=? AND keyword=?', (provider, '__provider__')).fetchone()
    return not row or utc(row[0]) <= at


def due_keywords(con, provider, keywords, at):
    """Read shared provider history once, rather than issuing queries per candidate."""
    if not provider_available(con, provider, at):
        return set()
    states = {r['keyword']: r for r in con.execute('SELECT * FROM provider_keyword_state WHERE provider=?', (provider,))}
    cooldowns = {r['keyword']: r['next_due'] for r in con.execute('SELECT keyword,next_due FROM feed_provider_cooldowns WHERE provider=?', (provider,))}
    observed = {r[0]: r[1] for r in con.execute("SELECT parent_keyword,max(observed_at) FROM keyword_suggestions WHERE source='google_suggest' GROUP BY parent_keyword")} if provider == 'google_suggest' else {}
    result = set()
    for keyword in keywords:
        if observed.get(keyword) and utc(observed[keyword]) <= at < utc(observed[keyword]) + timedelta(days=14):
            continue
        if keyword in cooldowns:
            ready = utc(cooldowns[keyword]) <= at
        elif keyword in states:
            row = states[keyword]
            ready = utc(row['last_attempt_at']) + (timedelta(hours=2) if row['status'] == 'failed' else timedelta(days=PROVIDERS.get(provider, 14))) <= at
        else:
            ready = True
        if ready:
            result.add(keyword)
    return result


def google_monthly_coverage(con, at=None):
    at = at or datetime.now(timezone.utc)
    direct = set(); shared = set()
    for row in con.execute("SELECT keyword,metadata_json FROM keyword_observations WHERE source='google_ads_keyword_planner' AND metric='monthly_searches' AND observed_at>=? AND observed_at<=?", ((at - timedelta(days=28)).isoformat(), at.isoformat())):
        direct.add(row[0]); shared.add(row[0])
        metadata = json.loads(row[1] or '{}')
        variants = metadata.get('close_variants', []) if isinstance(metadata, dict) else []
        shared.update(v for v in variants if isinstance(v, str))
    return direct, shared


def rebuild_candidates(con, focused=(), limit=500):
    from services.candidate_portfolio import screen_keyword, PROFESSION_TERMS
    focus = set(focused)
    now = datetime.now(timezone.utc)
    for keyword in focus:
        con.execute('INSERT OR IGNORE INTO seeds(keyword,domain,source,added_at) VALUES(?,?,?,?)', (keyword, 'validation', 'operator_watchlist', now.isoformat()))
    suggestions = {r[0] for r in con.execute('SELECT DISTINCT parent_keyword FROM keyword_suggestions')}
    listings = {r[0] for r in con.execute('SELECT DISTINCT keyword FROM keyword_listing_snapshots')}
    candidates = []
    for row in con.execute('SELECT keyword,domain,source FROM seeds'):
        keyword = row['keyword']; words = keyword.split(); reasons = []; priority = 0
        product = PRODUCTS.search(keyword)
        if keyword in focus:
            priority += 100; reasons.append('operator watchlist')
        if product:
            priority += 20; reasons.append('product phrase')
        if 2 <= len(words) <= 6:
            priority += 10; reasons.append('concise buyer phrase')
        if keyword in suggestions:
            priority += 10; reasons.append('autocomplete observed; volume unknown')
        if keyword in listings:
            priority += 30; reasons.append('listing sample observed')
        if ARTIFICIAL.search(keyword) and keyword not in focus:
            continue
        if not product and keyword not in focus:
            continue
        if len(keyword) > 100 or any(c in keyword for c in ',\r\n'):
            continue
        if screen_keyword(dict(row))['status'] == 'blocked' and keyword not in focus:
            continue
        content = [word.rstrip('s') for word in words if word not in {'for', 'with', 'the', 'a', 'and', 'of'}]
        if len(content) != len(set(content)):
            priority -= 20; reasons.append('repeated wording; lower priority')
        if any(re.search(r'\b' + re.escape(term) + r'\b', keyword) for term in PROFESSION_TERMS):
            priority += 10; reasons.append('specific buyer occupation')
        # Seasonal priority is a planning heuristic; never creates seasonality data.
        if now.month in {9, 10} and re.search(r'\b(fall|autumn|thanksgiving|christmas)\b', keyword):
            priority += 5; reasons.append('upcoming season')
        cluster = (product.group(0).rstrip('s') if product else 'watchlist')
        candidates.append((keyword, priority, reasons, cluster))
    candidates.sort(key=lambda r: (-r[1], r[0]))
    # Keep a bounded active shortlist and a separate small exploration lane.
    maximum = os.environ.get('FEED_MAX_COLLECTION') == '1'
    active_count = max(len(focus), 10000 if maximum else max(1, min(int(limit), 2000)))
    exploration_count = 1000 if maximum else 100
    if maximum:
        attempts = {r[0]: r[1] for r in con.execute("SELECT keyword,last_attempt_at FROM provider_keyword_state WHERE provider='etsy_open_api'")}
        # Keep priority leaders; rotate the remaining slots through unseen/oldest phrases.
        leaders = candidates[:max(len(focus), active_count // 4)]
        remaining = sorted(candidates[len(leaders):], key=lambda r: (attempts.get(r[0], ''), -r[1], r[0]))
        candidates = leaders + remaining
    con.execute('UPDATE feed_candidates SET tier="retained"')
    for index, (keyword, priority, reasons, cluster) in enumerate(candidates[:active_count + exploration_count]):
        con.execute('INSERT OR REPLACE INTO feed_candidates VALUES(?,?,?,?,?,?)',
                    (keyword, priority, 'active' if index < active_count else 'exploration', json.dumps(reasons), cluster, now.isoformat()))
    return min(len(candidates), active_count)


def next_batch(con, count, at=None):
    at = at or datetime.now(timezone.utc)
    result = []
    # Enforce budgets, rather than merely calculating an unused budget.
    budgets = [('refresh', count // 4), ('new', count - count // 4 - count // 5), ('exploration', count // 5)]
    rows = con.execute('''SELECT c.*,s.last_collected_at,p.last_attempt_at AS etsy_attempt FROM feed_candidates c
        LEFT JOIN keyword_collection_state s ON s.keyword=c.keyword
        LEFT JOIN provider_keyword_state p ON p.keyword=c.keyword AND p.provider='etsy_open_api'
        WHERE c.tier IN ('active','exploration') ORDER BY c.priority DESC,
        COALESCE(s.last_collected_at,''),c.keyword''').fetchall()
    lane_mode = os.environ.get('FEED_COLLECTION_LANE')
    providers = ('etsy_open_api',) if lane_mode == 'competition' else ('google_suggest',) if lane_mode == 'discovery' else ('etsy_open_api', 'google_suggest')
    ready = set().union(*(due_keywords(con, p, [r['keyword'] for r in rows], at) for p in providers))
    if os.environ.get('FEED_MAX_COLLECTION') == '1':
        _, measured = google_monthly_coverage(con, at)
        samples = {r[0] for r in con.execute('SELECT DISTINCT keyword FROM keyword_listing_snapshots WHERE observed_at>=?', ((at - timedelta(days=7)).isoformat(),))}
        rows.sort(key=lambda r: (0 if r['priority'] >= 100 else 1,
                                0 if r['keyword'] in (samples if lane_mode == 'discovery' else measured) else 1,
                                -r['priority'], r['last_collected_at'] or '', r['keyword']))
        if lane_mode == 'competition':
            from services.supported_keywords import RULES
            high_demand = set()
            for observation in con.execute("SELECT keyword,value,metadata_json FROM keyword_observations WHERE source='google_ads_keyword_planner' AND metric='monthly_searches' AND geography=? AND observed_at>=? ORDER BY observed_at,id", (RULES['geography'], (at-timedelta(days=28)).isoformat())):
                metadata = json.loads(observation['metadata_json'] or '{}')
                aliases = [observation['keyword'], *metadata.get('close_variants', [])] if isinstance(metadata, dict) else [observation['keyword']]
                for alias in aliases:
                    high_demand.discard(alias)
                    if observation['value'] is not None and observation['value'] >= RULES['google_minimum']:
                        high_demand.add(alias)
            rows.sort(key=lambda r: (r['priority'] < 100, r['keyword'] not in high_demand))
    for lane, budget in budgets:
        chosen = 0
        for row in rows:
            if chosen >= budget:
                break
            kw = row['keyword']
            if kw in result or kw not in ready:
                continue
            eligible = row['tier'] == 'exploration' if lane == 'exploration' else row['tier'] == 'active' and ((row['etsy_attempt'] is not None) == (lane == 'refresh'))
            if eligible and chosen < max(0, budget):
                result.append(kw); chosen += 1
    if os.environ.get('FEED_MAX_COLLECTION') == '1':
        # Preserve each lane's initial share, then lend idle capacity to eligible work.
        for row in rows:
            kw = row['keyword']
            if kw not in result and kw in ready:
                result.append(kw)
            if len(result) >= count:
                break
    return result[:count]


def coverage(con, at=None):
    at = at or datetime.now(timezone.utc)
    cutoff = (at - timedelta(hours=24)).isoformat()
    providers = []
    for row in con.execute('''SELECT provider,count(*) attempts,count(DISTINCT keyword) unique_keywords,
        sum(CASE WHEN row_count>0 THEN 1 ELSE 0 END) useful_attempts,
        sum(CASE WHEN status='no_data' THEN 1 ELSE 0 END) empty_attempts,
        sum(CASE WHEN status NOT IN ('completed','no_data','unchanged','partial') THEN 1 ELSE 0 END) failed_attempts,
        sum(row_count) entries FROM feed_provider_attempts WHERE attempted_at>=? GROUP BY provider''', (cutoff,)):
        value = dict(row); value['repeated_attempts'] = value['attempts'] - value['unique_keywords']; providers.append(value)
    sample_cutoff = (at - timedelta(days=7)).isoformat()
    google_cutoff = (at - timedelta(days=28)).isoformat()
    active = {r[0] for r in con.execute("SELECT keyword FROM feed_candidates WHERE tier='active'")}
    samples = {r[0] for r in con.execute('SELECT DISTINCT keyword FROM keyword_listing_snapshots WHERE observed_at>=?', (sample_cutoff,))}
    direct, shared = google_monthly_coverage(con, at)
    preview = []
    for row in con.execute("SELECT keyword,priority,cluster FROM feed_candidates WHERE tier='active' ORDER BY priority DESC,keyword LIMIT 10"):
        value = dict(row)
        value['competition_sample_current'] = bool(con.execute('SELECT 1 FROM keyword_listing_snapshots WHERE keyword=? AND observed_at>=? LIMIT 1', (row['keyword'], sample_cutoff)).fetchone())
        value['google_demand_measured'] = bool(con.execute("SELECT 1 FROM keyword_observations WHERE keyword=? AND source='google_ads_keyword_planner' AND metric='monthly_searches' AND observed_at>=? LIMIT 1", (row['keyword'], google_cutoff)).fetchone())
        preview.append(value)
    return {'window': 'rolling_24_hours', 'as_of': at.isoformat(), 'providers': providers,
            'library_keywords': con.execute('SELECT count(*) FROM seeds').fetchone()[0],
            'active_keywords': con.execute("SELECT count(*) FROM feed_candidates WHERE tier='active'").fetchone()[0],
            'exploration_keywords': con.execute("SELECT count(*) FROM feed_candidates WHERE tier='exploration'").fetchone()[0],
            'active_current_competition': len(active & samples),
            'active_google_monthly_direct': len(active & direct),
            'active_google_monthly_supported': len(active & shared),
            'active_paired_keywords': len(active & samples & shared),
            'candidate_preview': preview,
            'notes': ['Priority is a research heuristic, not a profit forecast.', 'Imported history is separate from new native attempts.', 'Suggestion entries and overlapping keyword demand are not additive sales demand.']}
