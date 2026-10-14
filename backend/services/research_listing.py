"""Free, deterministic listing drafts grounded in current evidence and user facts.

Drafts never publish or manufacture product attributes, images, prices or costs.
They share the existing revisioned private ledger and outcome workflow.
"""
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import re

from services import product_validation as validation
from services import supported_keywords as support


def research_connection():
    from pipeline import keyword_database as kdb
    path = Path(kdb.DB_PATH)
    if not path.exists():
        return None
    con = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def overview():
    con = research_connection()
    try:
        goal = support.overview(con, limit=200) if con else {'status': 'awaiting_collector', 'target': 3000, 'qualified_this_month': 0, 'candidates': []}
    finally:
        if con:
            con.close()
    # Drafts stay private; never write them into public keyword snapshots.
    goal['drafts'] = [{**row['payload'], 'id': row['id'], 'project_id': row['project_id'],
                       'sync_status': row['sync_status']} for row in validation.records(kind='listing_draft')]
    return goal


def current_candidate(keyword):
    con = research_connection()
    if con is None:
        raise ValueError('Research evidence is not installed')
    try:
        row = con.execute('SELECT * FROM feed_supported_keywords WHERE keyword=?', (keyword,)).fetchone()
        if not row:
            raise ValueError('Choose a supported keyword from the research queue')
        row = dict(row)
        evidence = json.loads(row['evidence_json'])
        at = datetime.now(timezone.utc)
        if row['status'] == 'needs_evidence' or not support.fresh(row['evaluated_at'], 1, at) or not support.fresh(evidence['competition_observed_at'], 7, at):
            raise ValueError('Refresh the qualification and competition evidence before drafting')
        if row['status'] == 'google_supported' and not support.fresh(evidence['google_observed_at'], 28, at):
            raise ValueError('Refresh supporting Google demand before drafting')
        if row['status'] == 'etsy_demand_backed' and (not support.fresh(evidence['etsy_marketplace']['observed_at'], 30, at) or not support.fresh(evidence['etsy_marketplace']['period_end'], 30, at)):
            raise ValueError('Refresh Etsy buyer demand before drafting')
        siblings = con.execute("SELECT keyword FROM feed_supported_keywords WHERE demand_group=? AND status!='needs_evidence' ORDER BY keyword", (row['demand_group'],)).fetchall()
        return {**evidence, 'status': row['status'], 'niche_key': row['niche_key'], 'demand_group': row['demand_group'],
                'supporting_keywords': [r['keyword'] for r in siblings if r['keyword'] != keyword][:14]}
    except sqlite3.OperationalError as exc:
        raise ValueError('The collector has not initialized supported keyword tracking') from exc
    finally:
        con.close()


def clean(value, name, maximum=300, required=False):
    if not isinstance(value, str):
        if value is None and not required:
            return ''
        raise ValueError(name + ' must be text')
    value = ' '.join(value.split())
    if len(value) > maximum or (required and not value):
        raise ValueError(f'{name} must contain 1–{maximum} characters' if required else name + ' is too long')
    return value


def tags_for(evidence, facts):
    candidates = [evidence['keyword'], *evidence['supporting_keywords']]
    # Preserve phrase boundaries; do not create word-salad tags across fields.
    for phrase in [*candidates, facts['product_name'], facts['material'], facts['color'], facts['size'], facts['personalization']]:
        words = re.findall(r"[a-z0-9]+", phrase.lower())
        for size in (3, 2, 1):
            candidates.extend(' '.join(words[i:i+size]) for i in range(len(words)-size+1))
    tags = []
    for value in candidates:
        value = support.normalized(value)
        if 2 <= len(value) <= 20 and value not in tags and value not in support.STOP:
            tags.append(value)
        if len(tags) == 13:
            break
    return tags


def attach_preserved_evidence(project_id, evidence):
    """Reuse exact native samples/packages; never recollect or auto-approve them."""
    con = research_connection()
    if con is None:
        return
    try:
        rows = con.execute('''SELECT * FROM keyword_listing_snapshots WHERE keyword=?
            AND source='etsy_open_api' AND collection_run_id=? ORDER BY position LIMIT 100''',
            (evidence['keyword'], evidence['competition_run_id'])).fetchall()
        listings = [{'listing_id': row['listing_id'], 'shop_id': row['shop_name'], 'title': row['title'],
                     'price': row['price'], 'currency': row['currency_code'], 'shipping': None}
                    for row in rows if row['listing_id'] and row['shop_name'] and row['title'] and
                    support.numeric(row['price']) is not None and row['currency_code']]
        if listings:
            validation.save_competitors(project_id, {'keyword': evidence['keyword'],
                'observed_at': evidence['competition_observed_at'][:10], 'source': 'Etsy Open API / preserved native collection',
                'filters': 'Native collection ' + str(evidence['competition_run_id']),
                'listings': listings, 'relevance_reviewed': False})
        google_run = evidence.get('google_run_id') or ''
        if google_run.startswith('google-feed:'):
            package = con.execute("SELECT payload FROM feed_import_records WHERE origin='google-packages' AND sha256=?", (google_run.removeprefix('google-feed:'),)).fetchone()
            if package:
                validation.import_google_package(project_id, {'package': json.loads(package['payload'])})
        market = evidence.get('etsy_marketplace')
        if market:
            validation.save_market(project_id, {'keyword': evidence['keyword'], 'searches': market['searches'],
                'listings': market['listings'], 'geography': market['geography'],
                'period_start': market['period_start'], 'period_end': market['period_end'],
                'observed_at': market['observed_at'][:10], 'source_note': 'Preserved Marketplace Insights; native collection ' + str(market['run_id'])})
    finally:
        con.close()


def audit(draft, project_id):
    blockers = ['Review the product, rights, title, tags and imagery before publication']
    if len(draft['tags']) != 13:
        blockers.append('Complete 13 relevant, unique tags of at most 20 characters')
    if not draft['facts']['category']:
        blockers.append('Select and verify the most specific Etsy category and attributes')
    if draft['facts']['price'] is None:
        blockers.append('Confirm the actual selling price')
    if not draft['facts']['delivery']:
        blockers.append('Confirm delivery, processing time and return terms')
    blockers.append('Attach and review actual product photos or mockups')
    project = validation.summary(project_id)
    economics = project.get('economics')
    if not economics or economics['conservative']['contribution_per_order'] is None:
        blockers.append('Complete conservative product economics')
    elif economics['conservative']['contribution_per_order'] <= 0:
        blockers.append('Conservative contribution must be positive')
    if draft['support']['status'] == 'google_supported':
        blockers.append('Etsy buyer demand remains unverified; use a controlled test')
    return {'status': 'draft_requires_review', 'can_publish': False, 'blockers': blockers,
            'title_characters': len(draft['title']), 'tag_count': len(draft['tags']),
            'title_under_15_words': len(draft['title'].split()) < 15,
            'keyword_supported': True, 'seo_ready': False, 'profit_validated': False}


@validation.single_writer
def create_draft(data):
    if not isinstance(data, dict):
        raise ValueError('Product facts must be an object')
    keyword = support.normalized(data.get('keyword'))
    evidence = current_candidate(keyword)
    facts = {name: clean(data.get(name), name.replace('_', ' '), 2000 if name == 'details' else 140 if name == 'product_name' else 300,
                         required=name in {'product_name', 'product_type', 'details'})
             for name in ('product_name', 'product_type', 'details', 'material', 'color', 'size', 'personalization', 'category', 'delivery')}
    if data.get('product_matches_keyword') is not True:
        raise ValueError('Confirm that the actual product satisfies this buyer keyword')
    if not support.tokens(keyword) & support.tokens(facts['product_name'] + ' ' + facts['details']):
        raise ValueError('Product facts must describe the selected buyer intent')
    facts['price'] = validation.number(data.get('price'), 'Price', optional=True)
    facts['currency'] = 'USD'
    if facts['price'] is not None and facts['price'] <= 0:
        raise ValueError('Price must be positive')
    supplied_tags = None
    if data.get('tags'):
        if not isinstance(data['tags'], str) or len(data['tags']) > 500:
            raise ValueError('Tags must be comma-separated text of at most 500 characters')
        supplied_tags = list(dict.fromkeys(support.normalized(tag) for tag in data['tags'].split(',') if tag.strip()))
        if len(supplied_tags) > 13 or any(not 2 <= len(tag) <= 20 for tag in supplied_tags):
            raise ValueError('Provide at most 13 unique tags, each 2–20 characters')
    # IDs represent actual distinct products, not keyword variants. Changes in
    # price/copy become revisions of the same product rather than extra listings.
    product_id = 'research-' + validation.digest({'product_name': support.normalized(facts['product_name']),
                                                 'product_type': support.normalized(facts['product_type'])})[:24]
    existing = validation.records(product_id, 'project')
    previous_keywords = existing[0]['payload']['keywords'] if existing else []
    keywords = list(dict.fromkeys(previous_keywords + [keyword, *evidence['supporting_keywords']]))[:15]
    project = {'name': facts['product_name'], 'product_type': facts['product_type'], 'keywords': keywords,
               'created_at': existing[0]['payload']['created_at'] if existing else validation.stamp(),
               'source': 'supported_keyword_research', 'shop_theme': existing[0]['payload']['shop_theme'] if existing else evidence['niche_key']}
    validation.put('project', product_id, project, product_id)
    attach_preserved_evidence(product_id, evidence)
    description = facts['product_name'] + '. ' + facts['details']
    attributes = {key: facts[key] for key in ('material', 'color', 'size', 'personalization') if facts[key]}
    if attributes:
        description += '\n\n' + '\n'.join(f'{key.capitalize()}: {value}' for key, value in attributes.items())
    if facts['delivery']:
        description += '\n\nDelivery and returns: ' + facts['delivery']
    draft = {'title': facts['product_name'], 'description': description, 'tags': supplied_tags if supplied_tags is not None else tags_for(evidence, facts),
             'category': facts['category'] or None, 'attributes': attributes, 'facts': facts, 'support': evidence,
             'support_fingerprint': validation.digest(evidence), 'model_version': 'etgen-research-listing-v1',
             'shop_theme': evidence['niche_key'], 'status': 'draft_requires_review'}
    draft['audit'] = audit(draft, product_id)
    result = validation.put('listing_draft', product_id, draft, product_id + ':listing')
    return {**result, 'project_id': product_id, 'draft': draft}


def export_draft(record_id):
    row = next((row for row in validation.records(kind='listing_draft') if row['id'] == record_id), None)
    if not row:
        raise ValueError('Draft not found')
    draft = row['payload']
    # Evidence can expire after drafting; recheck before every handoff.
    try:
        draft['support'] = current_candidate(draft['support']['keyword'])
        draft['audit'] = audit(draft, row['project_id'])
    except ValueError:
        draft['audit'] = {**draft['audit'], 'can_publish': False, 'keyword_supported': False,
                          'blockers': ['Refresh source evidence before using this draft', *draft['audit']['blockers']]}
    return {'record_id': row['id'], 'project_id': row['project_id'], 'draft': draft,
            'exported_at': validation.stamp(), 'publication_performed': False}
