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
from services import selling_discovery as discovery, feed_request_budget as budget


class SourceUnavailable(ValueError):
    pass


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

    def close(self):
        self.client.close()

    def get(self, path, scope, params=None):
        # Recheck the protected proof before each request, including expiry.
        if scope not in discovery.approval()['scopes'] or scope not in self.scopes:
            raise SourceUnavailable('authorization_unverified')
        if not re.fullmatch(r'/listings/[0-9]+(?:/reviews|/images)?|/shops/[0-9]+(?:/reviews)?', path):
            raise ValueError('Unsupported source path')
        page = scope == 'listing_pages'
        if page and not re.fullmatch(r'/listings/[0-9]+', path):
            raise ValueError('Unsupported page path')
        if params and (scope != 'listing_reviews' or set(params) - {'limit', 'min_created', 'max_created'}):
            raise ValueError('Unsupported source parameters')
        headers = {'User-Agent': 'EtGen/1.0 (permitted product research)', 'Accept': 'text/html' if page else 'application/json'}
        if not page:
            from adapters.research.etsy_open_api import _api_key_header
            key = _api_key_header()
            if not key:
                raise SourceUnavailable('credential_unavailable')
            headers['x-api-key'] = key
        identity = budget.claim(self.con, {}, self.batch_id, 15)
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
                    raise SourceUnavailable('access_denied' if response.status_code in (401, 403) else 'rate_limited' if response.status_code == 429 else 'source_unavailable')
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
                # Retain only public listing feature fields for the existing
                # read-only history bridge. Reviews, images, shops, HTML and
                # authentication headers never enter this saved response.
                if (scope == 'listing_api' and re.fullmatch(r'/listings/[0-9]+', path)
                        and isinstance(payload, dict) and str(payload.get('listing_id')) == path.split('/')[2]):
                    fields = ('listing_id', 'title', 'shop_id', 'taxonomy_id', 'listing_type',
                              'original_creation_timestamp', 'views', 'num_favorers', 'quantity')
                    public = {k: payload[k] for k in fields if k in payload and isinstance(payload[k], (str, int, float, type(None)))}
                    if isinstance(payload.get('price'), dict):
                        public['price'] = {k: v for k, v in payload['price'].items()
                            if k in ('amount', 'divisor', 'currency_code') and isinstance(v, (str, int, float, type(None)))}
                    saved_listing = gzip.compress(json.dumps(public, allow_nan=False).encode())
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
    ref = f'https://www.etsy.com/listing/{identity}'
    if 'listing_api' in client.scopes:
        data = client.get(f'/listings/{identity}', 'listing_api')
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
                    basis='point_in_time' if metric == 'stock' else 'lifetime', observed_at=at, source='etsy_public', source_ref=ref))
        price = data.get('price')
        if isinstance(price, dict) and price.get('divisor', 0) > 0:
            observations.append(Observation(listing_id=identity, metric='price', value=price['amount'] / price['divisor'],
                currency=price['currency_code'], observed_at=at, source='etsy_public', source_ref=ref))
        if 'shop_api' in client.scopes and str(data.get('shop_id', '')).isdecimal():
            shop = client.get('/shops/' + str(data['shop_id']), 'shop_api')
            listing['shop'] = shop.get('shop_name') or listing['shop']
            # Shop review_count can cover the past year. Do not mislabel it as
            # lifetime reviews or use a mismatched review/sales conversion ratio.
            for key, metric in [('transaction_sold_count', 'shop_sales')]:
                if shop.get(key) is not None:
                    observations.append(Observation(listing_id=identity, metric=metric, value=shop[key], basis='lifetime',
                        observed_at=at, source='etsy_public', source_ref='https://www.etsy.com/shop/' + listing['shop'],
                        note='Shop-wide counter. Never allocate this total as listing orders.'))
    if 'listing_reviews' in client.scopes:
        start = at - timedelta(days=30)
        review_path = f'/listings/{identity}/reviews'
        review_params = {'limit': 100, 'min_created': int(start.timestamp()), 'max_created': int(at.timestamp())}
        data = client.get(review_path, 'listing_reviews', review_params)
        # Etsy can return an empty listing review set despite shop reviews.
        # The documented shop-review endpoint retains each review's listing ID.
        # Match that identity, never assign unrelated shop reviews to a product.
        shop_fallback = False
        if data.get('results') == [] and shop_id.isdecimal() and 'shop_api' in client.scopes:
            review_path = f'/shops/{shop_id}/reviews'
            data = client.get(review_path, 'listing_reviews', review_params)
            shop_fallback = True
        results = data.get('results')
        if not isinstance(results, list) or len(results) > 100:
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
            if len(text.strip()) < 3:
                continue
            reviews.append(Review(review_id=digest([identity, timestamp, review['rating'], text])[:40],
                listing_id=identity, reviewed_on=when.date(),
                rating=review['rating'], text=text, source_ref=ref + '/reviews'))
        reported = data.get('count')
        complete = (not malformed and isinstance(reported, int) and not isinstance(reported, bool)
                    and reported == len(results) and len(results) < 100)
        review_window = {'start': start.isoformat(), 'end': at.isoformat(), 'review_times': sorted(times),
                         'observed_reviews': len(times), 'reported_count': reported if isinstance(reported, int) and not isinstance(reported, bool) and reported >= 0 else None,
                         'complete': complete, 'limit': 100,
                         'source_ref': 'https://api.etsy.com/v3/application' + review_path,
                         'response_scope': 'shop_reviews_matched_by_listing_id' if shop_fallback else 'listing_reviews',
                         'completeness_basis': 'bounded_response_count_matches_rows' if complete else 'truncated_or_unverified_response'}
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
        estimator.record_capture(packet, discovery.now(), review_window)
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
                rows = estimator.due_rows(target, discovery.now().isoformat())
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
                    except budget.CollectionDeferred:
                        return {'status': 'budget_deferred', 'requests': client.requests}
                    except (SourceUnavailable, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                        status = str(exc) if isinstance(exc, SourceUnavailable) else 'unsupported_response'
                    delay = 6 if status in ('api_updated', 'purchase_message_observed', 'purchase_message_unavailable') else 24
                    next_check = (discovery.now()+timedelta(hours=delay)).isoformat()
                    target.execute('UPDATE candidates SET checked_at=?,check_status=?,next_check=? WHERE listing_id=?',
                        (discovery.now().isoformat(), status, next_check, row['listing_id']))
                    target.commit()
                    estimator.record_check(row['listing_id'], status, next_check)
                    if status in ('access_denied', 'rate_limited', 'access_challenge', 'authorization_unverified'):
                        break
                return {'status': 'completed', 'requests': client.requests}
            finally:
                client.close()
