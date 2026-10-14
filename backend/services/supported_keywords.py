"""Evidence-backed keyword qualification, with durable, deduplicated monthly credit.

Rules are screening heuristics, not predicted sales. Only the collector writes
this ledger; the operator API reads it. Existing evidence is baseline, never new
monthly production. Historical evidence and first qualification survive refresh.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import calendar
import json
import math
import re

VERSION = 'etgen-supported-keywords-v1'
RULES = {'monthly_target': 3000, 'google_minimum': 500, 'maximum_listings': 3000,
         'sample_target': 50, 'minimum_relevance': .7, 'competition_days': 7,
         'google_days': 28, 'marketplace_days': 30, 'etsy_minimum': 300,
         'etsy_minimum_ratio': .2, 'geography': 'US'}
STOP = {'a', 'an', 'the', 'for', 'of', 'with', 'and', 'to', 'best', 'gift', 'gifts', 'idea', 'ideas'}
SYNONYMS = {'mugs': 'mug', 'cups': 'mug', 'cup': 'mug', 'shirts': 'shirt', 'tees': 'shirt',
            'tee': 'shirt', 'tshirt': 'shirt', 'programmer': 'coder', 'programmers': 'coder',
            'coding': 'coder', 'developer': 'coder', 'developers': 'coder', 'personalised': 'personalized',
            'custom': 'personalized', 'teachers': 'teacher', 'nurses': 'nurse', 'stickers': 'sticker',
            'decals': 'decal', 'prints': 'print', 'posters': 'poster', 'ornaments': 'ornament',
            'totes': 'tote', 'bags': 'bag', 'signs': 'sign', 'hangers': 'hanger', 'planners': 'planner'}


def normalized(value):
    return ' '.join(str(value or '').casefold().split())


def tokens(value):
    return {SYNONYMS.get(word, word) for word in re.findall(r'[a-z0-9]+', normalized(value)) if word not in STOP}


def parsed(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def numeric(value):
    try:
        number = float(value)
        return number if not isinstance(value, bool) and math.isfinite(number) and number >= 0 else None
    except (ValueError, TypeError):
        return None


def fresh(value, days, at):
    timestamp = parsed(value)
    return timestamp is not None and at - timedelta(days=days) <= timestamp <= at


def schema(con):
    con.execute('''CREATE TABLE IF NOT EXISTS feed_support_control(name TEXT PRIMARY KEY,value TEXT NOT NULL)''')
    con.execute('''CREATE TABLE IF NOT EXISTS feed_supported_keywords(
        keyword TEXT PRIMARY KEY, demand_group TEXT NOT NULL, niche_key TEXT NOT NULL,
        first_supported_at TEXT, baseline INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL, evaluated_at TEXT NOT NULL, evidence_json TEXT NOT NULL,
        first_evidence_json TEXT)''')
    con.execute('CREATE INDEX IF NOT EXISTS feed_support_month ON feed_supported_keywords(first_supported_at,demand_group)')


def demand_groups(con):
    """Union all known close variants, including older groups, before counting."""
    parents = {}
    def root(word):
        parents.setdefault(word, word)
        while parents[word] != word:
            parents[word] = parents[parents[word]]
            word = parents[word]
        return word
    for row in con.execute("SELECT keyword,metadata_json FROM keyword_observations WHERE source='google_ads_keyword_planner' AND metric='monthly_searches'"):
        try:
            metadata = json.loads(row['metadata_json'] or '{}')
            aliases = metadata.get('close_variants', []) if isinstance(metadata, dict) else []
        except (ValueError, TypeError):
            aliases = []
        words = [normalized(row['keyword']), *[normalized(v) for v in aliases if isinstance(v, str)]]
        words = [word for word in words if word]
        for word in words[1:]:
            a, b = root(words[0]), root(word)
            parents[max(a, b)] = min(a, b)
        if words:
            root(words[0])
    return {word: root(word) for word in parents}


def observations(con, at):
    """Keep the newest row per exact source/scope/metric, including nulls/zeroes."""
    latest = {}
    since = (at - timedelta(days=30)).isoformat()
    rows = con.execute('''SELECT * FROM keyword_observations WHERE observed_at>=? AND
        ((source='etsy_open_api' AND metric='listing_count') OR
         (source='google_ads_keyword_planner' AND metric='monthly_searches') OR
         (source='etsy_marketplace_insights' AND metric IN ('searches','listing_count')))
        ORDER BY observed_at,id''', (since,))
    for row in rows:
        row = dict(row)
        if parsed(row['observed_at']) is None or parsed(row['observed_at']) > at:
            continue
        latest[(normalized(row['keyword']), row['source'], row['metric'], row['geography'] or '')] = row
    return latest


def evaluate(keyword, google, supply, samples, market, seed, at):
    from services.candidate_portfolio import screen_keyword
    blockers = []
    checked = screen_keyword(seed)
    if checked['status'] != 'pass':
        blockers.append('Product intent or rights require review')
    years = [int(v) for v in re.findall(r'\b20\d{2}\b', keyword)]
    if any(year < at.year for year in years):
        blockers.append('Past-year wording requires review')
    if not fresh((supply or {}).get('observed_at'), RULES['competition_days'], at):
        blockers.append('Current Etsy competition missing')
    count = numeric((supply or {}).get('value'))
    if count is None or count <= 0 or count > RULES['maximum_listings']:
        blockers.append('Etsy listing count must be 1–3,000')
    sample = {row['listing_id']: row for row in samples if row['listing_id'] and fresh(row['observed_at'], 7, at)}
    sample = list(sample.values())
    required = min(RULES['sample_target'], int(count)) if count and count > 0 else RULES['sample_target']
    if len(sample) < required:
        blockers.append(f'Collect {required} comparable listing samples')
    terms = tokens(keyword)
    # Deliberately lexical: this is an automated relevance screen, not human approval.
    relevant = [row for row in sample if terms and len(terms & tokens(row['title'])) / len(terms) >= .7]
    relevance = len(relevant) / len(sample) if sample else None
    if relevance is None or relevance < RULES['minimum_relevance']:
        blockers.append('Automated sample relevance below 70%')
    google_valid = (google and google.get('geography') == RULES['geography'] and
                    fresh(google['observed_at'], RULES['google_days'], at) and
                    numeric(google['value']) is not None and numeric(google['value']) >= RULES['google_minimum'] and
                    parsed(google.get('period_start')) and parsed(google.get('period_end')) and
                    parsed(google['period_start']) <= parsed(google['period_end']) <= at)
    etsy_pair = None
    # Never combine supply/demand from different reporting windows or geographies.
    for searches, listings in market:
        start, end = parsed(searches['period_start']), parsed(searches['period_end'])
        demand, total = numeric(searches['value']), numeric(listings['value'])
        if (fresh(searches['observed_at'], 30, at) and fresh(listings['observed_at'], 30, at) and
            start and end and start <= end <= at and end >= at - timedelta(days=30) and
            searches['period_start'] == listings['period_start'] and searches['period_end'] == listings['period_end'] and
            searches['geography'] == listings['geography'] and demand is not None and total and
            demand >= 300 and total <= 3000 and demand / total >= .2):
            etsy_pair = {'searches': demand, 'listings': total, 'ratio': round(demand / total, 4),
                         'geography': searches['geography'], 'period_start': searches['period_start'],
                         'period_end': searches['period_end'], 'observed_at': searches['observed_at'],
                         'run_id': searches['collection_run_id']}
            break
    if not google_valid and not etsy_pair:
        blockers.append('Supporting demand missing or below threshold')
    shops = Counter(row['shop_name'] for row in relevant if row['shop_name'])
    concentration = sum(n for _, n in shops.most_common(5)) / len(relevant) if relevant and shops else None
    evidence = {'keyword': keyword, 'google_monthly_searches': numeric(google['value']) if google else None,
                'google_geography': google.get('geography') if google else None,
                'google_observed_at': google.get('observed_at') if google else None,
                'google_run_id': google.get('collection_run_id') if google else None,
                'etsy_listing_count': count, 'competition_observed_at': (supply or {}).get('observed_at'),
                'competition_run_id': (supply or {}).get('collection_run_id'),
                'sample_count': len(sample), 'relevant_sample_count': len(relevant),
                'automated_relevance': relevance, 'top_five_shop_share': concentration,
                'etsy_marketplace': etsy_pair, 'blockers': blockers, 'model_version': VERSION,
                'human_relevance_review_required': True, 'profit_validated': False}
    return ('etsy_demand_backed' if etsy_pair else 'google_supported') if not blockers else 'needs_evidence', evidence


def refresh(con, at=None):
    at = at or datetime.now(timezone.utc)
    schema(con)
    initial = not con.execute("SELECT 1 FROM feed_support_control WHERE name='baseline_at'").fetchone()
    if initial:
        con.execute("INSERT INTO feed_support_control VALUES('baseline_at',?)", (at.isoformat(),))
    groups = demand_groups(con)
    latest = observations(con, at)
    states = {(row['keyword'], row['provider']): dict(row) for row in con.execute('SELECT * FROM provider_keyword_state')}
    google = {}
    for (_, source, _, geo), row in latest.items():
        if source == 'google_ads_keyword_planner' and geo == RULES['geography']:
            try:
                metadata = json.loads(row['metadata_json'] or '{}')
            except (TypeError, ValueError):
                metadata = {}
            aliases = metadata.get('close_variants', []) if isinstance(metadata, dict) else []
            for word in [row['keyword'], *[v for v in aliases if isinstance(v, str)]]:
                word = normalized(word)
                if word not in google or parsed(row['observed_at']) >= parsed(google[word]['observed_at']):
                    google[word] = row
    for word, row in list(google.items()):
        state = states.get((word, 'google_ads_keyword_planner'))
        if state and state['status'] in {'failed', 'no_data'} and parsed(state['last_attempt_at']) and parsed(row['observed_at']) <= parsed(state['last_attempt_at']) <= at:
            google[word] = {**row, 'value': None}
    seeds = {normalized(r['keyword']): dict(r) for r in con.execute('SELECT * FROM seeds')}
    supply = {key[0]: row for key, row in latest.items() if key[1] == 'etsy_open_api' and fresh(row['observed_at'], 7, at)}
    for word, row in list(supply.items()):
        state = states.get((word, 'etsy_open_api'))
        if state and state['status'] in {'failed', 'no_data'} and parsed(state['last_attempt_at']) and parsed(row['observed_at']) <= parsed(state['last_attempt_at']) <= at:
            supply[word] = {**row, 'value': None}
    marketplace = defaultdict(list)
    for key, row in latest.items():
        if key[1] == 'etsy_marketplace_insights' and key[2] == 'searches':
            listing = latest.get((key[0], key[1], 'listing_count', key[3]))
            if listing:
                marketplace[key[0]].append((row, listing))
    samples = defaultdict(list)
    eligible = set(supply) & (set(google) | set(marketplace))
    words = sorted(eligible)
    for index in range(0, len(words), 400):
        batch = words[index:index+400]
        for row in con.execute('SELECT * FROM keyword_listing_snapshots WHERE source=\'etsy_open_api\' AND observed_at>=? AND keyword IN (' + ','.join('?' for _ in batch) + ')', [(at-timedelta(days=7)).isoformat(), *batch]):
            # The sample and count must come from the same collection, not stitched history.
            if row['collection_run_id'] == supply[row['keyword']]['collection_run_id']:
                samples[row['keyword']].append(dict(row))
    con.execute("UPDATE feed_supported_keywords SET status='needs_evidence'")
    for keyword in sorted(eligible):
        seed = seeds.get(keyword, {'keyword': keyword})
        status, evidence = evaluate(keyword, google.get(keyword), supply[keyword], samples[keyword], marketplace[keyword], seed, at)
        group = groups.get(keyword, keyword)
        niche = ' '.join(sorted(tokens(keyword)))
        encoded = json.dumps(evidence, sort_keys=True, allow_nan=False)
        qualified = status != 'needs_evidence'
        con.execute('''INSERT INTO feed_supported_keywords VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(keyword) DO UPDATE SET demand_group=excluded.demand_group,niche_key=excluded.niche_key,
            first_supported_at=COALESCE(feed_supported_keywords.first_supported_at,excluded.first_supported_at),
            baseline=max(feed_supported_keywords.baseline,excluded.baseline),status=excluded.status,
            evaluated_at=excluded.evaluated_at,evidence_json=excluded.evidence_json,
            first_evidence_json=COALESCE(feed_supported_keywords.first_evidence_json,excluded.first_evidence_json)''',
            (keyword, group, niche, at.isoformat() if qualified else None, int(initial and qualified), status,
             at.isoformat(), encoded, encoded if qualified else None))
    # A newly discovered alias may join two formerly separate groups. Reconcile
    # retained credit too, rather than counting that family twice next month.
    for row in con.execute('SELECT keyword,demand_group FROM feed_supported_keywords').fetchall():
        group = groups.get(row['keyword'], row['keyword'])
        if group != row['demand_group']:
            con.execute('UPDATE feed_supported_keywords SET demand_group=? WHERE keyword=?', (group, row['keyword']))
    con.execute("INSERT INTO feed_support_control VALUES('last_evaluated_at',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (at.isoformat(),))
    return overview(con, at)


def overview(con, at=None, limit=50):
    at = at or datetime.now(timezone.utc)
    exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='feed_supported_keywords'").fetchone()
    if not exists:
        return {'status': 'awaiting_collector', 'target': 3000, 'qualified_this_month': 0, 'candidates': []}
    rows = [dict(row) for row in con.execute('SELECT * FROM feed_supported_keywords')]
    families = defaultdict(list)
    for row in rows:
        families[row['demand_group']].append(row)
    first = {}; baseline = 0
    for group, members in families.items():
        qualified_dates = [parsed(row['first_supported_at']) for row in members if parsed(row['first_supported_at'])]
        if any(row['baseline'] for row in members):
            baseline += 1
        elif qualified_dates:
            first[group] = min(qualified_dates)
    month_start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_days = calendar.monthrange(at.year, at.month)[1]
    month_end = month_start + timedelta(days=month_days)
    credited = sum(month_start <= value <= at for value in first.values())
    last_week = sum(at-timedelta(days=7) <= value <= at for value in first.values())
    pace = last_week / 7
    days_remaining = max((month_end-at).total_seconds()/86400, 1/24)
    candidates = []
    for members in families.values():
        current = [row for row in members if row['status'] != 'needs_evidence' and fresh(row['evaluated_at'], 1, at)]
        if not current:
            continue
        best = sorted(current, key=lambda row: (row['status'] != 'etsy_demand_backed', row['keyword']))[0]
        evidence = json.loads(best['evidence_json'])
        if not fresh(evidence['competition_observed_at'], 7, at):
            continue
        if best['status'] == 'google_supported' and not fresh(evidence['google_observed_at'], 28, at):
            continue
        if best['status'] == 'etsy_demand_backed' and (not fresh(evidence['etsy_marketplace']['observed_at'], 30, at) or not fresh(evidence['etsy_marketplace']['period_end'], 30, at)):
            continue
        candidates.append({**evidence, 'demand_group': best['demand_group'], 'niche_key': best['niche_key'],
                           'status': best['status'], 'supporting_keywords': sorted(row['keyword'] for row in current if row['keyword'] != best['keyword'])[:14]})
    candidates.sort(key=lambda row: (row['status'] != 'etsy_demand_backed', -(row['google_monthly_searches'] or 0), row['etsy_listing_count'], row['keyword']))
    shortages = Counter(blocker for row in rows if row['status'] == 'needs_evidence' for blocker in json.loads(row['evidence_json'])['blockers'])
    return {'status': 'tracking', 'model_version': VERSION, 'as_of': at.isoformat(), 'month': at.strftime('%Y-%m'),
            'timezone': 'UTC', 'target': 3000, 'qualified_this_month': credited, 'baseline_groups': baseline,
            'available_supported_groups': len(candidates), 'available_niches': len({row['niche_key'] for row in candidates}),
            'etsy_demand_backed_groups': sum(row['status']=='etsy_demand_backed' for row in candidates),
            'new_groups_last_7_days': last_week, 'observed_daily_pace': round(pace, 2),
            'required_daily_pace': math.ceil(max(0, 3000-credited)/days_remaining),
            'projected_month_total': int(credited+pace*days_remaining), 'projection_basis': 'last_7_days_observed_not_a_guarantee',
            'rules': RULES, 'candidates': candidates[:max(1,min(limit,200))],
            'blockers': [{'reason': reason, 'keywords': count} for reason, count in shortages.most_common(6)],
            'notes': ['Existing supported groups are baseline, not new monthly production.',
                      'Close variants count once; refreshes do not earn new credit.',
                      'Google supports external demand, not exact Etsy searches.',
                      'Automated relevance is a lexical screen; human product review remains required.']}
