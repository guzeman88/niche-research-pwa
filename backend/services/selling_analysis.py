"""Explainable product research. No sales inference from interest or stock changes."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, date
import re

MODEL = 'etgen-selling-products-v1'
THEMES = {
    'readability': (r'\b(read|readable|font|text|contrast|tiny|small print)\b', 'Improve text hierarchy, contrast and readable print sizes.'),
    'instructions': (r'\b(instruction|instructions|confusing|tutorial|directions)\b', 'Provide clear instructions and a worked example.'),
    'formats': (r'\b(a4|letter|size|sizes|format|formats|pdf|png)\b', 'Test the requested sizes and file formats before promising them.'),
    'personalization': (r'\b(personalization|personalisation|personalized|custom|name|names)\b', 'Make supported personalization choices and their limits clear.'),
    'usability': (r'\b(space|room|writing|use|usable|layout|missing|pages)\b', 'Improve the buyer task, writing space and useful contents.'),
    'quality': (r'\b(blurry|pixelated|resolution|quality|print|printing)\b', 'Inspect real output at its intended print size.'),
    'delivery': (r'\b(shipping|delivery|late|arrived|package)\b', 'Investigate fulfillment or delivery; this may not be a design problem.'),
    'value': (r'\b(price|expensive|worth|value|bundle)\b', 'Compare the useful contents and actual costs before changing the offer.'),
}
STOP = set('a an the and or for of with to in on by is it this that gift gifts personalized custom digital download printable'.split())


def timestamp(value):
    return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)


def words(value):
    return re.findall(r'[a-z0-9]+', value.casefold())


def analyze(listings, observations, reviews, patterns, at=None):
    at = at or datetime.now(timezone.utc)
    cutoff = at - timedelta(days=30)
    by_id = {row['listing_id']: row for row in listings}
    latest = {}
    series = defaultdict(list)
    for row in observations:
        key = (row['listing_id'], row['metric'], row['source'], row['basis'], row.get('keyword', '').casefold(), row.get('geography', ''))
        series[key].append(row)
        if key not in latest or timestamp(row['observed_at']) > timestamp(latest[key]['observed_at']):
            latest[key] = row

    conflicts = []
    for key, values in series.items():
        newest = latest[key]
        ties = [row for row in values if row['observed_at'] == newest['observed_at']]
        if len({row['value'] for row in ties}) > 1:
            conflicts.append({'listing_id': key[0], 'metric': key[1], 'source': key[2],
                              'observations': ties, 'status': 'conflicting_latest_values'})
            latest[key] = {**newest, 'value': None}
    # Estimates from separate providers are alternatives, never summed together.
    recent_sales, historical_sales, interest = [], [], []
    for row in latest.values():
        if row['value'] is None:
            continue
        if row['metric'] in ('estimated_sales', 'seller_reported_sales'):
            current = (timestamp(row['observed_at']) >= cutoff and row['basis'] == 'period'
                       and date.fromisoformat(row['period_start']) >= cutoff.date())
            target = recent_sales if current else historical_sales
            target.append({**row, 'scope': 'listing', 'independently_verified': False})
        elif row['metric'] in ('reviews', 'favorites', 'shop_sales'):
            interest.append({**row, 'scope': 'shop' if row['metric'] == 'shop_sales' else 'listing'})
    recent_review_listings = {r['listing_id'] for r in reviews if date.fromisoformat(r['reviewed_on']) >= cutoff.date()}
    active = {r['listing_id'] for r in recent_sales if r['value'] > 0}
    shops = {by_id[key]['shop'].casefold() for key in active if key in by_id and by_id[key]['shop']}
    evidence = ('seller_reported_sales' if any(r['metric'] == 'seller_reported_sales' and r['value'] > 0 for r in recent_sales)
                else 'estimated_recent_sales' if active else 'recent_reviews' if recent_review_listings
                else 'interest_only' if interest else 'historical_estimates' if historical_sales else 'needs_evidence')

    momentum = []
    for key, values in series.items():
        values.sort(key=lambda row: timestamp(row['observed_at']))
        last = values[-1]
        # A newer missing value makes the series unknown rather than reviving old data.
        if len(values) < 2 or latest[key]['value'] is None or timestamp(last['observed_at']) < cutoff:
            continue
        old = values[-2]
        if old['value'] is None or timestamp(old['observed_at']).date() == timestamp(last['observed_at']).date():
            continue
        metric = last['metric']
        if metric not in ('estimated_sales', 'seller_reported_sales', 'reviews', 'favorites', 'shop_sales', 'price'):
            continue
        comparable = True
        overlap = False
        if last['basis'] == 'period':
            days = lambda row: (date.fromisoformat(row['period_end']) - date.fromisoformat(row['period_start'])).days + 1
            comparable = days(old) == days(last)
            overlap = old['period_end'] >= last['period_start']
        if metric == 'price' and old['currency'] != last['currency']:
            comparable = False
        delta = last['value'] - old['value']
        reset = metric in ('reviews', 'favorites', 'shop_sales') and delta < 0
        momentum.append({'listing_id': key[0], 'metric': metric, 'source': last['source'], 'basis': last['basis'],
                         'from': old['observed_at'], 'to': last['observed_at'],
                         'before': old['value'], 'after': last['value'],
                         'change': delta if comparable and not reset else None,
                         'status': 'counter_decreased' if reset else 'incomparable_windows' if not comparable else 'comparable',
                         'overlapping_windows': overlap, 'currency': last['currency'],
                         'scope': 'shop' if metric == 'shop_sales' else 'listing'})

    themes = {}
    for name, (expression, suggestion) in THEMES.items():
        matched = [r for r in reviews if re.search(expression, r['text'], re.I)]
        concerns = [r for r in matched if r['rating'] <= 3 or re.search(r'\b(wish|missing|however|but|would prefer|could be)\b', r['text'], re.I)]
        good = [r for r in matched if r not in concerns]
        if matched:
            concern_listings = {r['listing_id'] for r in concerns}
            themes[name] = {'positive': len(good), 'concerns': len(concerns),
                'independent_listings': len(concern_listings),
                'independent_shops': len({by_id[r]['shop'].casefold() for r in concern_listings if r in by_id and by_id[r]['shop']}),
                'review_ids': [r['review_id'] for r in concerns],
                'suggestion': suggestion, 'repeated': len(concerns) >= 2 and len(concern_listings) >= 2,
                'scope': 'fulfillment' if name == 'delivery' else 'product_or_offer'}

    terms = defaultdict(set)
    term_shops = defaultdict(set)
    for listing in listings:
        found = set(tag.casefold() for tag in listing.get('tags', []))
        tokens = words(listing['title'])
        for length in (2, 3):
            for index in range(len(tokens) - length + 1):
                phrase = tokens[index:index + length]
                if phrase[0] not in STOP and phrase[-1] not in STOP:
                    found.add(' '.join(phrase))
        for phrase in found:
            terms[phrase].add(listing['listing_id'])
            if listing['shop']:
                term_shops[phrase].add(listing['shop'].casefold())
    demand = [r for r in latest.values() if r['metric'] == 'keyword_searches']
    keywords = [{'keyword': term, 'listings': len(ids), 'shops': len(term_shops[term]),
                 'measurements': [r for r in demand if r.get('keyword', '').casefold() == term],
                 'sales_attribution': 'unknown'} for term, ids in sorted(terms.items(), key=lambda item: (-len(item[1]), item[0]))[:40]]

    feature_counts = Counter(feature for row in patterns for feature in set(row['features']))
    matrix = [{**row, 'title': by_id.get(row['listing_id'], {}).get('title', row['listing_id']),
               'recent_sales_signal': row['listing_id'] in active} for row in patterns]
    suggestions = [value['suggestion'] for value in themes.values() if value['repeated']]
    if any(row.get('readability') is not None and row['readability'] <= 2 for row in patterns):
        suggestions.append('Test a clearer original layout; low readability is an operator assessment, not a measured conversion problem.')
    if not suggestions:
        suggestions = ['Record a specific buyer need or a testable improvement before creating a product.']
    methods = {
        'bestsellers': {'status': 'available' if recent_sales or historical_sales else 'needs_evidence',
                        'recent': recent_sales, 'historical': historical_sales},
        'momentum': {'status': 'available' if momentum else 'needs_evidence', 'series': momentum},
        'reviews': {'status': 'available' if reviews else 'needs_evidence', 'themes': themes,
                    'recent_listing_count': len(recent_review_listings)},
        'keywords': {'status': 'available' if keywords else 'needs_evidence', 'terms': keywords, 'demand': demand},
        'patterns': {'status': 'available' if patterns else 'needs_evidence', 'matrix': matrix,
                     'features': dict(feature_counts), 'missing_traits_are_unknown': True},
    }
    return {'model': MODEL, 'as_of': at.isoformat(), 'evidence_level': evidence,
            'recent_sales_listing_count': len(active), 'independent_selling_shops': len(shops),
            'listing_count': len(listings), 'review_count': len(reviews),
            'methods': methods, 'conflicts': conflicts, 'improvement_suggestions': list(dict.fromkeys(suggestions)),
            'limitations': ['Research signals do not establish profit or sales attribution to a keyword.',
                'Seller-reported figures are not independently verified; provider estimates are not order records.',
                'Review dates can lag purchases. Favorites, shop totals and stock changes are not listing sales.',
                'Theme matching and visual attributes require human review; no competitor artwork is recreated.']}
