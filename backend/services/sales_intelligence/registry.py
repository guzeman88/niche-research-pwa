"""Dated source dispositions. Marketing quotas do not enable collection or training."""
import json
from . import store

# Distinct brands are recorded, including duplicates and unsuitable leads.
SEEDS = [
 ('muadzo', 'MuaDzo', 'unverified', 'muadzo', '15 daily lookups advertised; no supported automated feed verified', 'https://muadzo.com/terms'),
 ('hive', 'Hive / Exto', 'unverified', 'exto', '10 daily browser analyses; no export/API verified', 'https://exto.help/legal/terms'),
 ('ehunt', 'EHunt / EtsyHunt', 'unverified', 'ehunt', 'Free web/CSV access needs verification; official API trial requires purchasing a plan; no free automated feed', 'https://api.ehunt.ai/service-api'),
 ('erank', 'eRank', 'blocked_permission', 'erank', 'Terms restrict automated extraction and competing use', 'https://erank.com/legal/terms-of-service'),
 ('rankhero', 'RankHero / EtsyCheck', 'blocked_permission', 'rankhero', 'Lifetime estimates; terms restrict automation and competing use', 'https://www.rankhero.com/terms'),
 ('koalanda', 'Koalanda', 'blocked_permission', 'koalanda', 'Terms prohibit scraping; automated/model reuse not established', 'https://koalanda.pro/terms'),
 ('insightfactory', 'InsightFactory', 'unverified', 'insight_family_unresolved', '15 one-time credits; no supported free feed verified', 'https://insightfactory.app/'),
 ('insightagent', 'Insight Agent', 'unverified', 'insight_family_unresolved', '15 one-time credits; relationship to InsightFactory unresolved', 'https://www.insightagent.app/guides'),
 ('cashcowly', 'CashCowly', 'unverified', 'cashcowly', 'Website lists free estimates but official extension listing calls them premium; access/export/reuse unresolved', 'https://www.cashcowly.io/'),
 ('toolsy', 'Toolsy', 'blocked_permission', 'toolsy', '50 one-time credits; database compilation/automation/competing-use restrictions', 'https://toolsy.io/terms-conditions'),
 ('listadum', 'Listadum', 'unverified', 'listadum', 'Free extension; sales fields uncertain and API/export paid', 'https://www.listadum.com/pricing'),
 ('etsimator', 'EtsiMator', 'unverified', 'etsimator', 'Conflicting free quota; no functioning documented API contract verified', 'https://etsimator.com/'),
 ('sellfinch', 'SellFinch', 'unverified', 'etsimator', 'Install link resolves to EtsiMator; not an independent provider', 'https://sellfinch.com/'),
 ('sellerbowl', 'SellerBowl', 'unverified', 'sellerbowl', 'Unpacked extension; method, free Etsy access and reuse unverified', 'https://sellerbowl.com/tools/chrome-extension'),
 ('ranketsy', 'RankEtsy', 'blocked_cost', 'ranketsy', 'Free plan excludes competitor sales; trial renewal unverified', 'https://www.ranketsy.com/'),
 ('alura', 'Alura', 'unverified', 'alura', 'Official free-plan descriptions conflict about sales estimates', 'https://www.alura.io/contact-us'),
 ('everbee', 'EverBee', 'blocked_cost', 'everbee', 'Free plan excludes sales/revenue; no free trial', 'https://www.everbee.io/pricing'),
 ('salesamurai', 'Sale Samurai', 'blocked_cost', 'salesamurai', 'Card-renewing trial excluded by free-only policy', 'https://beta.salesamurai.io/price'),
 ('marmalead', 'Marmalead', 'auxiliary_only', 'marmalead', 'Keyword research; suitable free listing sales data not established', 'https://marmalead.com/free-trial/'),
 ('zeuslens', 'ZEUS / ZeusLens', 'blocked_cost', 'zeus', 'Sales estimates require paid access', 'https://zeusseller.com/tutorials/'),
 ('teom', 'TEOM', 'unavailable', 'teom', 'Readable live access could not be verified', 'https://teomcloud.com/'),
 ('etsy_oracle', 'etsy-oracle', 'unavailable', 'etsy_oracle', 'Estimator remains roadmap work', 'https://github.com/brainbytes-dev/etsy-oracle'),
 ('apify', 'Apify sales estimator', 'blocked_permission', 'apify', 'Free credits do not resolve marketplace collection authorization', 'https://apify.com/marielise.dev/etsy-sales-intelligence'),
 ('nichescope', 'NicheScope', 'auxiliary_only', 'nichescope', 'Competition data; deliberately supplies no sales estimates', 'https://nichescope.uk/'),
]


def grants():
    """Protected operator-maintained evidence, never writable through a browser toggle."""
    path = store.root() / 'access.json'
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (ValueError, OSError):
        return {}


def permission(source_id, capability, at=None):
    at = at or store.now()
    if source_id == 'native_catalog':
        return capability in ('storage', 'comparison', 'training')
    item = grants().get(source_id, {})
    try:
        return bool(item.get('reference') and item.get('account_ref')
                    and store.stamp(item['issued_at']) <= at < store.stamp(item['expires_at'])
                    and capability in item.get('capabilities', []) and item.get('free_only') is True)
    except (ValueError, TypeError, KeyError):
        return False


def sources(only=None):
    with store.database() as con:
        overrides = {r['id']: json.loads(r['payload']) for r in con.execute('SELECT * FROM sources')}
        health = {ident: store.get_control(con, 'source_health:' + ident, {'status': 'no_successful_collection'}) for ident, *_ in SEEDS}
    result = []
    for ident, name, disposition, group, reason, url in SEEDS:
        if only is not None and ident != only:
            continue
        entry = {'id': ident, 'name': name, 'disposition': disposition, 'group': group,
                 'reason': reason, 'url': url, 'reviewed_on': '2026-10-17', **overrides.get(ident, {})}
        entry['capabilities'] = {key: permission(ident, key) for key in ('storage', 'comparison', 'training', 'export', 'automated')}
        from .adapters import configuration
        try:
            configuration(ident)
            entry['automation'] = 'supported_api_configured'
        except (ValueError, TypeError):
            entry['automation'] = 'export_ingestion_only' if permission(ident, 'storage') else 'not_verified'
        entry['paused'] = bool(overrides.get(ident, {}).get('paused', False))
        entry['health'] = health[ident]
        grant = grants().get(ident, {})
        entry['access_review_at'] = grant.get('expires_at') if entry['capabilities']['storage'] else None
        from . import quotas
        try:
            with store.database() as con:
                allowance = quotas.state(con, ident)
            entry['allowance'] = {k: v for k, v in allowance.items() if k not in ('account_ref', 'quota_source')}
        except (ValueError, KeyError, TypeError):
            entry['allowance'] = None
        result.append(entry)
    return result


def source(source_id):
    item = next(iter(sources(source_id)), None)
    if not item:
        raise ValueError('Unknown reference source')
    return item


def pause(source_id, value):
    source(source_id)
    with store.database(True) as con:
        row = con.execute('SELECT payload FROM sources WHERE id=?', (source_id,)).fetchone()
        item = json.loads(row[0]) if row else {}
        item['paused'] = value
        con.execute('INSERT INTO sources VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (source_id, store.encoded(item)))
        store.audit(con, 'source_pause', {'source_id': source_id, 'paused': value})
    return {'paused': value, 'source_id': source_id}
