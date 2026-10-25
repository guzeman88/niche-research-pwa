"""Scoped source adapters. No hidden endpoints, proxy rotation or anti-bot bypass."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import gzip
import json
import re
import sqlite3
import time
from html.parser import HTMLParser

import httpx
from models.selling_products import Listing, Observation, Review, Packet
from services.sales_model import parse_message
from services import selling_discovery as discovery, feed_request_budget as budget, selling_collection as cache


class SourceUnavailable(ValueError):
    def __init__(self, reason, status=None):
        super().__init__(reason)
        self.status = status


def purchase_message(document, listing_id):
    """Only the main listing's cart region; recommendations/JSON scripts excluded.

    Unsupported or changed markup yields unknown, never a page-wide regex match.
    HTML shape is fixture-tested; a live permitted capture is still required.
    """
    class VisibleCart(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.canonical, self.found = [], [], {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'link' and attrs.get('rel') == 'canonical':
                self.canonical.append(attrs.get('href', ''))
            if tag in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
                return
            parent = self.stack[-1] if self.stack else {}
            hidden = parent.get('hidden', False) or tag in ('script', 'style', 'noscript') or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
            self.stack.append({'tag': tag, 'hidden': hidden, 'cart': parent.get('cart', False) or attrs.get('id') == 'listing-page-cart', 'chunks': []})

        def handle_data(self, data):
            for frame in self.stack:
                if frame['cart'] and not frame['hidden'] and not self.stack[-1]['hidden']:
                    frame['chunks'].append(data.strip())

        def handle_endtag(self, tag):
            if not self.stack or self.stack[-1]['tag'] != tag:
                return
            frame = self.stack.pop()
            raw = ' '.join(' '.join(frame['chunks']).split())
            if frame['cart'] and not frame['hidden'] and tag in ('p', 'span', 'div') and len(raw) <= 500:
                try:
                    self.found[raw] = parse_message(raw)
                except ValueError:
                    pass

    parser = VisibleCart()
    parser.feed(document)
    pattern = r'https://www\.etsy\.com/(?:[a-z]{2}/)?listing/' + re.escape(listing_id) + r'(?:/[^?#]*)?'
    if len(parser.canonical) != 1 or not re.fullmatch(pattern, parser.canonical[0]):
        return None
    return next(iter(parser.found.items())) if len(parser.found) == 1 else None


class Client:
    """Counts every attempted API/page call in the native collector's same ledger."""
    def __init__(self, con, batch_id, scopes, client=None):
        self.con, self.batch_id, self.scopes = con, batch_id, set(scopes)
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)
        self.requests = 0
        self.last_call = 0.0
        self.optimized = True
        self.prefetched = {}
        self.review_windows = {}
        self.cache_hits = 0
        self.batch_limit = 40

    def prefetch(self, rows):
        if 'listing_api' not in self.scopes:
            return
        identities = [r['listing_id'] for r in rows][:25]
        missing=[]
        for identity in identities:
            item=cache.cached('listing:'+identity)
            if item:
                self.prefetched[identity]=item
                self.cache_hits+=1
            else:
                missing.append(identity)
        identities=missing
        if not identities:
            return
        disabled = cache.control('batch_disabled_until')
        if disabled and discovery._time(disabled)>discovery.now():
            return
        includes = 'Images,Shop' if 'shop_api' in self.scopes else 'Images'
        try:
            payload = self.get('/listings/batch','listing_api',{'listing_ids':','.join(identities),'includes':includes})
        except SourceUnavailable as exc:
            if exc.status in (400,404):
                if exc.status == 400:
                    cache.control('batch_disabled_until',value=(discovery.now()+timedelta(hours=6)).isoformat())
                return  # Counted, bounded individual fallback; never retry 403/429.
            raise
        values = payload.get('results')
        if not isinstance(values,list) or len(values)>len(identities):
            raise SourceUnavailable('unsupported_batch_response')
        seen = set()
        for value in values:
            identity = str(value.get('listing_id','')) if isinstance(value,dict) else ''
            if identity not in identities or identity in seen:
                raise SourceUnavailable('listing_identity_mismatch')
            shop=value.get('shop',value.get('Shop'))
            if isinstance(shop,dict) and shop.get('shop_id') is not None and str(shop['shop_id'])!=str(value.get('shop_id')):
                raise SourceUnavailable('shop_identity_mismatch')
            seen.add(identity)
        for value in values:
            identity = str(value['listing_id'])
            public = {**cache.public_listing(value),'_captured_at':discovery.now().isoformat()}
            self.prefetched[identity] = public
            cache.save('listing:'+identity,public,hours=1)
            if isinstance(public.get('shop'),dict) and str(public.get('shop_id','')).isdecimal():
                cache.save('shop:'+str(public['shop_id']),public['shop'])

    def close(self):
        self.client.close()

    def get(self, path, scope, params=None):
        # Recheck the protected proof before each request, including expiry.
        if scope not in discovery.approval()['scopes'] or scope not in self.scopes:
            raise SourceUnavailable('authorization_unverified')
        if not re.fullmatch(r'/listings/(?:batch|[0-9]+(?:/reviews|/images)?)|/shops/[0-9]+(?:/reviews)?', path):
            raise ValueError('Unsupported source path')
        page = scope == 'listing_pages'
        if page and not re.fullmatch(r'/listings/[0-9]+', path):
            raise ValueError('Unsupported page path')
        if params:
            allowed = ({'limit','offset','min_created','max_created'} if scope=='listing_reviews' else
                       {'listing_ids','includes'} if scope=='listing_api' and path=='/listings/batch' else set())
            if set(params)-allowed:
                raise ValueError('Unsupported source parameters')
            if path=='/listings/batch' and (not re.fullmatch(r'[0-9]+(?:,[0-9]+){0,24}',str(params.get('listing_ids','')))
                    or params.get('includes') not in ('Images','Images,Shop') or ('Shop' in params['includes'] and 'shop_api' not in self.scopes)):
                raise ValueError('Unsupported batch parameters')
        if scope=='listing_api' and re.fullmatch(r'/listings/[0-9]+(?:/images)?',path):
            identity = path.split('/')[2]
            if identity in self.prefetched:
                item = self.prefetched[identity]
                if not path.endswith('/images') or 'images' in item:
                    self.cache_hits += 1
                    return {'results':item['images']} if path.endswith('/images') else item
        if scope=='shop_api' and re.fullmatch(r'/shops/[0-9]+',path):
            item = cache.cached('shop:'+path.split('/')[2])
            if item:
                self.cache_hits += 1
                return item
        headers = {'User-Agent': 'EtGen/1.0 (permitted product research)', 'Accept': 'text/html' if page else 'application/json'}
        if not page:
            from adapters.research.etsy_open_api import _api_key_header
            key = _api_key_header()
            if not key:
                raise SourceUnavailable('credential_unavailable')
            headers['x-api-key'] = key
        identity = budget.claim(self.con, {}, self.batch_id, self.batch_limit)
        self.requests += 1
        quota = budget.latest_quota(self.con)
        # One request/second at most, and slower if provider reports a lower QPS.
        interval = max(1.0, 1.0 / max(float(quota.get('limit_per_second') or 1), .01))
        delay = interval - (time.monotonic() - self.last_call)
        if delay > 0:
            time.sleep(min(delay, 20))
        self.last_call = time.monotonic()
        url = ('https://www.etsy.com/listing/' + path.split('/')[2] if page
               else 'https://api.etsy.com/v3/application' + path)
        status, body, saved_listing = 'transport_error', b'', None
        try:
            with self.client.stream('GET', url, headers=headers, params=params) as response:
                status = str(response.status_code)
                for name, field in [('x-limit-per-day', 'limit_per_day'), ('x-remaining-today', 'remaining_today'), ('x-limit-per-second', 'limit_per_second')]:
                    if not page and response.headers.get(name, '').isdigit():
                        quota[field] = int(response.headers[name])
                if response.status_code in (403, 429):
                    retry = response.headers.get('retry-after', '')
                    quota['retry_after_until'] = time.time() + (max(3600, min(int(retry), 86400)) if retry.isdigit() else 3600)
                if response.status_code != 200:
                    raise SourceUnavailable('access_denied' if response.status_code in (401, 403) else 'rate_limited' if response.status_code == 429 else 'source_unavailable',response.status_code)
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > 3_000_000:
                        status = 'body_too_large'
                        raise SourceUnavailable('unsupported_response')
                if page:
                    text = body.decode('utf-8', errors='replace')
                    if 'captcha' in text.casefold() or 'datadome' in text.casefold():
                        status = 'challenge'
                        quota['retry_after_until'] = time.time() + 3600
                        raise SourceUnavailable('access_challenge')
                    return text
                payload = json.loads(body)
                if not isinstance(payload,dict):
                    raise SourceUnavailable('unsupported_response')
                if scope=='shop_api' and re.fullmatch(r'/shops/[0-9]+',path):
                    if payload.get('shop_id') is not None and str(payload['shop_id'])!=path.split('/')[2]:
                        raise SourceUnavailable('shop_identity_mismatch')
                    cache.save('shop:'+path.split('/')[2],cache.public_shop(payload))
                # Retain only public listing feature fields for the existing
                # read-only history bridge. Reviews, images, shops, HTML and
                # authentication headers never enter this saved response.
                if (scope == 'listing_api' and re.fullmatch(r'/listings/[0-9]+', path)
                        and isinstance(payload, dict) and str(payload.get('listing_id')) == path.split('/')[2]):
                    cache.save('listing:'+str(payload['listing_id']),cache.public_listing(payload),hours=1)
                    fields = ('listing_id', 'title', 'shop_id', 'taxonomy_id', 'listing_type',
                              'original_creation_timestamp', 'views', 'num_favorers', 'quantity')
                    public = {k: payload[k] for k in fields if k in payload and isinstance(payload[k], (str, int, float, type(None)))}
                    if isinstance(payload.get('price'), dict):
                        public['price'] = {k: v for k, v in payload['price'].items()
                            if k in ('amount', 'divisor', 'currency_code') and isinstance(v, (str, int, float, type(None)))}
                    saved_listing = gzip.compress(json.dumps(public, allow_nan=False).encode())
                if scope=='listing_api' and path=='/listings/batch':
                    values=payload.get('results')
                    wanted=set(str(params['listing_ids']).split(','))
                    if isinstance(values,list) and len(values)<=len(wanted) and all(isinstance(v,dict) and str(v.get('listing_id')) in wanted for v in values):
                        fields=('listing_id','title','shop_id','taxonomy_id','listing_type','original_creation_timestamp',
                                'views','num_favorers','quantity')
                        clean=[]
                        for value in values:
                            public={k:value[k] for k in fields if k in value and isinstance(value[k],(str,int,float,type(None)))}
                            if isinstance(value.get('price'),dict):
                                public['price']={k:v for k,v in value['price'].items() if k in ('amount','divisor','currency_code') and isinstance(v,(str,int,float,type(None)))}
                            clean.append(public)
                        saved_listing=gzip.compress(json.dumps({'results':clean},allow_nan=False).encode())
                return payload
        finally:
            quota['captured_at'] = discovery.now().isoformat()
            self.con.execute('UPDATE feed_etsy_requests SET status=?,quota_json=?,request_json=?,response_gzip=? WHERE id=?',
                             (status, json.dumps(quota), json.dumps({'path': path, 'scope': scope, 'params': params}), saved_listing, identity))
            self.con.commit()


def collect(client, row, retain_estimator=False):
    identity = row['listing_id']
    packet = json.loads(row['packet'])
    listing = dict(packet['listings'][0])
    observations, reviews = [], []
    review_window = None
    shop_id = ''
    at = discovery.now()
    metadata_at, attributes = at.isoformat(), {}
    ref = f'https://www.etsy.com/listing/{identity}'
    if 'listing_api' in client.scopes:
        data = client.get(f'/listings/{identity}', 'listing_api')
        metadata_at = data.get('_captured_at') or at.isoformat()
        attributes = {k:data[k] for k in ('state','materials','is_personalizable','description','updated_timestamp') if k in data}
        if str(data.get('listing_id')) != identity:
            raise SourceUnavailable('listing_identity_mismatch')
        shop_id = str(data.get('shop_id') or '')
        listing.update(title=data['title'], tags=data.get('tags') or [], source='etsy_public', source_ref=ref)
        listing.update(category=str(data.get('taxonomy_id') or ''),
                       product_type={'physical': 'physical', 'download': 'digital'}.get(data.get('listing_type'), 'unknown'))
        if data.get('original_creation_timestamp'):
            listing['created_on'] = datetime.fromtimestamp(data['original_creation_timestamp'], timezone.utc).date().isoformat()
        images = client.get(f'/listings/{identity}/images', 'listing_api').get('results', [])
        if images:
            listing['image_url'] = images[0].get('url_570xN') or images[0].get('url_fullxfull') or ''
        for key, metric in [('num_favorers', 'favorites'), ('views', 'views'), ('quantity', 'stock')]:
            if data.get(key) is not None:
                observations.append(Observation(listing_id=identity, metric=metric, value=data[key],
                    basis='point_in_time' if metric == 'stock' else 'lifetime', observed_at=metadata_at, source='etsy_public', source_ref=ref))
        price = data.get('price')
        if isinstance(price, dict) and price.get('divisor', 0) > 0:
            observations.append(Observation(listing_id=identity, metric='price', value=price['amount'] / price['divisor'],
                currency=price['currency_code'], observed_at=metadata_at, source='etsy_public', source_ref=ref))
        if 'shop_api' in client.scopes and str(data.get('shop_id', '')).isdecimal():
            shop = client.get('/shops/' + str(data['shop_id']), 'shop_api')
            listing['shop'] = shop.get('shop_name') or listing['shop']
            # Shop review_count can cover the past year. Do not mislabel it as
            # lifetime reviews or use a mismatched review/sales conversion ratio.
            for key, metric in [('transaction_sold_count', 'shop_sales')]:
                if shop.get(key) is not None:
                    observations.append(Observation(listing_id=identity, metric=metric, value=shop[key], basis='lifetime',
                        observed_at=shop.get('_captured_at') or at, source='etsy_public', source_ref='https://www.etsy.com/shop/' + listing['shop'],
                        note='Shop-wide counter. Never allocate this total as listing orders.'))
    if 'listing_reviews' in client.scopes:
        start = at - timedelta(days=30)
        review_path = f'/listings/{identity}/reviews'
        review_params = {'limit': 100, 'min_created': int(start.timestamp()), 'max_created': int(at.timestamp())}
        review_job = None
        optimized = getattr(client,'optimized',False)
        if optimized:
            # One dated shop window supplies every exact listing ID in it.
            review_path = f'/shops/{shop_id}/reviews' if shop_id.isdecimal() and 'shop_api' in client.scopes else review_path
            review_job = cache.reviews(client,review_path,at)
            start = datetime.fromtimestamp(review_job['start'],timezone.utc)
            at = datetime.fromtimestamp(review_job['end'],timezone.utc)
            data = {'results':review_job['rows'],'count':len(review_job['rows'])}
        else:
            data = client.get(review_path, 'listing_reviews', review_params)
        # Etsy can return an empty listing review set despite shop reviews.
        # The documented shop-review endpoint retains each review's listing ID.
        # Match that identity, never assign unrelated shop reviews to a product.
        shop_fallback = optimized and review_path.startswith('/shops/')
        if not optimized and data.get('results') == [] and shop_id.isdecimal() and 'shop_api' in client.scopes:
            review_path = f'/shops/{shop_id}/reviews'
            data = client.get(review_path, 'listing_reviews', review_params)
            shop_fallback = True
        results = data.get('results')
        if not isinstance(results, list) or len(results) > (cache.MAX_REVIEW_ROWS if optimized else 100):
            raise SourceUnavailable('unsupported_review_response')
        times, event_ids, malformed = [], set(), False
        for review in results:
            if not isinstance(review, dict):
                malformed = True
                continue
            if str(review.get('listing_id')) != identity:
                if not shop_fallback or not str(review.get('listing_id', '')).isdecimal():
                    malformed = True
                continue
            if shop_fallback and str(review.get('shop_id', shop_id)) != shop_id:
                malformed = True
                continue
            from services.product_validation import digest
            timestamp = review.get('create_timestamp', review.get('created_timestamp'))
            if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
                malformed = True
                continue
            rating = review.get('rating')
            if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
                malformed = True
                continue
            try:
                when = datetime.fromtimestamp(timestamp, timezone.utc)
            except (ValueError, OverflowError, OSError):
                malformed = True
                continue
            if not start < when <= at:
                malformed = True
                continue
            # Transaction IDs are hashed locally solely to detect duplicate API
            # rows; no buyer identities or raw transaction identifiers persist.
            event_id = digest([identity, review.get('transaction_id'), timestamp, review.get('rating'), review.get('review')])
            if event_id in event_ids:
                malformed = True
                continue
            event_ids.add(event_id)
            times.append(when.isoformat())
            # Retain no buyer identities. Review IDs derive from public content/time.
            text = review.get('review') or ''
            # The research packet is deliberately small; the resumable job and
            # estimator retain every validated numeric review event separately.
            if len(text.strip()) < 3 or len(reviews)>=50:
                continue
            reviews.append(Review(review_id=digest([identity, timestamp, review['rating'], text])[:40],
                listing_id=identity, reviewed_on=when.date(),
                rating=review['rating'], text=text, source_ref=ref + '/reviews'))
        reported = data.get('count')
        complete = (not malformed and isinstance(reported, int) and not isinstance(reported, bool)
                    and reported == len(results) and len(results) < 100)
        if review_job:
            complete = not malformed and review_job['status']=='complete'
        review_window = {'start': start.isoformat(), 'end': at.isoformat(), 'review_times': sorted(times),
                         'observed_reviews': len(times), 'reported_count': reported if isinstance(reported, int) and not isinstance(reported, bool) and reported >= 0 else None,
                         'complete': complete, 'limit': 100,
                         'source_ref': 'https://api.etsy.com/v3/application' + review_path,
                         'response_scope': 'shop_reviews_matched_by_listing_id' if shop_fallback else 'listing_reviews',
                         'completeness_basis': review_job['reason'] if review_job else 'bounded_response_count_matches_rows' if complete else 'truncated_or_unverified_response',
                         **({'pages':review_job['pages'],'pending':review_job['status']=='pending'} if review_job else {})}
    page_status = 'api_updated'
    if 'listing_pages' in client.scopes:
        message = purchase_message(client.get(f'/listings/{identity}', 'listing_pages'), identity)
        page_status = 'purchase_message_observed' if message else 'purchase_message_unavailable'
        if message:
            raw, parsed = message
            observations.append(Observation(listing_id=identity, metric='purchase_message', value=parsed['value'],
                observed_at=at, source='etsy_public', source_ref=ref, raw_message=raw,
                unit=parsed['unit'], precision=parsed['precision'], window_hours=parsed['window_hours']))
    packet = Packet(listings=[Listing.model_validate(listing)], observations=observations, reviews=reviews).model_dump(mode='json')
    if retain_estimator:
        from services.sales_intelligence import estimator
        estimator.record_capture(packet, discovery.now(), review_window, metadata_at=metadata_at, attributes=attributes)
        if review_window and review_window['complete'] and shop_fallback:
            estimator.follow_reviewed_products(results, start, at, shop_id, identity, listing)
    return packet, page_status


def refresh_sources(run_id):
    access = discovery.approval()
    path = discovery.native_database()
    if not access['scopes'] or path is None:
        return {'status': 'authorization_unverified' if not access['scopes'] else 'catalog_unavailable', 'requests': 0}
    from services.app_keyword_feed import supervisor_lock
    with supervisor_lock(discovery.native_root() / 'worker.lock') as acquired:
        if not acquired:
            return {'status': 'native_collector_running', 'requests': 0}
        state_path = discovery.native_root() / 'state.sqlite'
        if state_path.is_file():
            with closing(sqlite3.connect(state_path.as_uri() + '?mode=ro', uri=True)) as state:
                if state.execute("SELECT value FROM control WHERE name='paused'").fetchone():
                    return {'status': 'collection_paused', 'requests': 0}
        with closing(sqlite3.connect(path, timeout=20)) as native, closing(discovery.connect()) as target:
            budget.schema(native)
            client = Client(native, 'selling-discovery-' + str(run_id), access['scopes'])
            try:
                from services.sales_intelligence import estimator
                estimator.expand_panel(target)
                rows = estimator.due_rows(target, discovery.now().isoformat(),limit=20)
                client.prefetch(rows)
                captures = 0
                for row in rows:
                    status = 'source_unavailable'
                    try:
                        if isinstance(row, dict) and row.get('pending_metadata') and 'listing_api' not in client.scopes:
                            continue
                        packet, status = collect(client, row, retain_estimator=True)
                        # A review-led product has no observed buyer keyword.
                        # Use its actual seller tag/title only as a research seed,
                        # never as measured search-demand evidence.
                        listing = packet['listings'][0]
                        seed = row['keyword'] or next((t for t in listing['tags'] if len(t)>=3), listing['title'])[:160]
                        discovery._upsert(target, packet, seed, discovery.now().isoformat())
                        captures += 1
                    except budget.CollectionDeferred:
                        return {'status': 'budget_deferred', 'requests': client.requests}
                    except (SourceUnavailable, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                        status = str(exc) if isinstance(exc, SourceUnavailable) else 'unsupported_response'
                    delay = estimator.check_delay(row['listing_id'],status)
                    next_check = (discovery.now()+timedelta(hours=delay)).isoformat()
                    target.execute('UPDATE candidates SET checked_at=?,check_status=?,next_check=? WHERE listing_id=?',
                        (discovery.now().isoformat(), status, next_check, row['listing_id']))
                    target.commit()
                    estimator.record_check(row['listing_id'], status, next_check)
                    if status in ('access_denied', 'rate_limited', 'access_challenge', 'authorization_unverified'):
                        break
                result = {'status': 'completed', 'requests': client.requests,'products_checked':captures,'cache_hits':client.cache_hits,
                          'allocation':budget.allocation(native,client.batch_id)}
                cache.control('last_pass',value={**result,'at':discovery.now().isoformat()})
                return result
            except budget.CollectionDeferred:
                return {'status':'budget_deferred','requests':client.requests}
            except (SourceUnavailable, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                return {'status':str(exc) if isinstance(exc,SourceUnavailable) else 'unsupported_response','requests':client.requests}
            finally:
                client.close()
