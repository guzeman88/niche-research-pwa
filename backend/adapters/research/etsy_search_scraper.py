"""
Etsy Search Scraper — no API key required.
Scrapes Etsy search results pages to extract real listing data:
  - Prices (full distribution, not just average)
  - Review counts when Etsy exposes them
  - Star Seller / Bestseller badges when Etsy exposes them
  - Shop names, listing titles, listing IDs

Missing observations remain ``None``. This adapter deliberately does not infer
sales, revenue, or a competition score from reviews or listing counts.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import random

import httpx

# Rotating user agents — Etsy 403s come from a stale/single UA fingerprint
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def _random_headers() -> dict:
    ua = random.choice(_USER_AGENTS)
    return {
        "User-Agent": ua,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }


_SEARCH_URL = "https://www.etsy.com/search"
_REQUEST_DELAY = 2.5   # seconds between requests — polite crawling
_MAX_RETRIES = max(1, int(os.environ.get("ETSY_HTML_MAX_RETRIES", "1") or "1"))
_FALLBACK_TIMEOUT = float(os.environ.get("ETSY_HTML_FALLBACK_TIMEOUT_SECONDS", "8") or "8")
_BLOCK_COOLDOWN_SECONDS = float(os.environ.get("ETSY_HTML_BLOCK_COOLDOWN_SECONDS", "1800") or "1800")
_BLOCKED_UNTIL = 0.0
_BLOCK_REASON = ""


class EtsyHtmlBlockedError(RuntimeError):
    """Raised when Etsy blocks no-key HTML scraping from this network."""


def is_etsy_html_blocked() -> bool:
    return time.monotonic() < _BLOCKED_UNTIL


def get_etsy_html_block_reason() -> str:
    if not is_etsy_html_blocked():
        return ""
    remaining = max(0, int(_BLOCKED_UNTIL - time.monotonic()))
    return f"{_BLOCK_REASON} (cooldown {remaining}s)"


def mark_etsy_html_blocked(reason: str, cooldown_seconds: float | None = None) -> None:
    global _BLOCKED_UNTIL, _BLOCK_REASON
    _BLOCK_REASON = reason
    _BLOCKED_UNTIL = time.monotonic() + (cooldown_seconds or _BLOCK_COOLDOWN_SECONDS)


def _html_scraper_enabled() -> bool:
    value = os.environ.get("ETSY_HTML_SCRAPER_ENABLED", "0").strip().lower()
    return value in {"1", "true", "yes"}


def _looks_like_challenge(status_code: int, text: str) -> bool:
    if status_code not in (403, 429):
        return False
    lowered = text[:1000].lower()
    return (
        "please enable js" in lowered
        or "please enable javascript" in lowered
        or "captcha" in lowered
        or "challenge" in lowered
        or status_code == 429
    )


@dataclass
class EtsyListingData:
    listing_id: str
    title: str
    price_usd: float
    review_count: int | None
    is_star_seller: bool | None
    is_bestseller: bool | None
    shop_name: str
    url: str
    num_favorites: int | None = None


@dataclass
class PriceDistribution:
    min: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    max: float | None = None
    mean: float | None = None
    sweet_spot: str | None = None

    @classmethod
    def from_prices(cls, prices: list[float]) -> "PriceDistribution":
        if not prices:
            return cls()
        s = sorted(prices)
        n = len(s)
        p25 = s[max(0, n // 4)]
        p75 = s[min(n - 1, (3 * n) // 4)]
        return cls(
            min=round(s[0], 2),
            p25=round(p25, 2),
            median=round(statistics.median(s), 2),
            p75=round(p75, 2),
            max=round(s[-1], 2),
            mean=round(statistics.mean(s), 2),
            sweet_spot=f"${p25:.0f}–${p75:.0f} (middle 50%)",
        )


@dataclass
class EtsySearchResult:
    keyword: str
    total_listing_count: int | None
    listings: list[EtsyListingData] = field(default_factory=list)
    price_distribution: PriceDistribution = field(default_factory=PriceDistribution)
    # Aggregate metrics
    avg_review_count: float | None = None
    pct_star_sellers: float | None = None
    pct_bestsellers: float | None = None
    competition_quality_score: None = None
    estimated_total_monthly_revenue_usd: None = None
    avg_favorites: float | None = None
    max_favorites: int | None = None
    pct_high_favorites: float | None = None
    error: str = ""

    def compute_aggregates(self) -> None:
        if not self.listings:
            return
        prices = [l.price_usd for l in self.listings if l.price_usd > 0]
        if prices:
            self.price_distribution = PriceDistribution.from_prices(prices)
        reviews = [l.review_count for l in self.listings if l.review_count is not None]
        if reviews:
            self.avg_review_count = round(sum(reviews) / len(reviews), 1)
        star_seller_values = [l.is_star_seller for l in self.listings if l.is_star_seller is not None]
        if star_seller_values:
            self.pct_star_sellers = round(sum(1 for value in star_seller_values if value) / len(star_seller_values) * 100, 1)
        bestseller_values = [l.is_bestseller for l in self.listings if l.is_bestseller is not None]
        if bestseller_values:
            self.pct_bestsellers = round(sum(1 for value in bestseller_values if value) / len(bestseller_values) * 100, 1)
        favs = [l.num_favorites for l in self.listings if l.num_favorites is not None]
        if favs:
            self.avg_favorites = round(sum(favs) / len(favs), 1)
            self.max_favorites = max(favs)


class EtsySearchScraper:
    """
    Scrapes Etsy search results pages to extract real listing-level data.
    No API key required. Respects rate limits via request delays.
    """

    def __init__(self, request_delay: float = _REQUEST_DELAY):
        self._delay = request_delay
        # Don't set headers at client level — rotate per-request
        self._client = httpx.Client(timeout=25, follow_redirects=True)

    def search(
        self,
        keyword: str,
        max_listings: int = 20,
        page: int = 1,
    ) -> EtsySearchResult:
        """Fetch and parse Etsy search results for a keyword."""
        result = EtsySearchResult(keyword=keyword, total_listing_count=None)
        try:
            html = self._fetch(keyword, page)
            listings, total_count = _parse_listings(html, max_listings)
            result.total_listing_count = total_count
            result.listings = listings
            result.compute_aggregates()
        except Exception as exc:
            result.error = str(exc)
        if not is_etsy_html_blocked():
            time.sleep(self._delay)
        return result

    def search_paged(
        self,
        keyword: str,
        max_pages: int = 3,
        max_listings: int = 60,
    ) -> EtsySearchResult:
        """
        Fetch multiple search result pages and merge into one result.
        Deduplicates by listing_id so Etsy's promoted re-inserts don't skew stats.
        60 listings gives a statistically representative price/competition picture
        vs. the top-20 which over-represents promoted/bestseller listings.
        """
        result = EtsySearchResult(keyword=keyword, total_listing_count=None)
        seen_ids: set[str] = set()
        all_listings: list[EtsyListingData] = []
        for page in range(1, max_pages + 1):
            try:
                html = self._fetch(keyword, page)
                if page == 1:
                    result.total_listing_count = _extract_total_count(html)
                page_listings, _ = _parse_listings(html, max_listings)
                new_on_page = 0
                for listing in page_listings:
                    if listing.listing_id and listing.listing_id not in seen_ids:
                        seen_ids.add(listing.listing_id)
                        all_listings.append(listing)
                        new_on_page += 1
                # Stop early if page returned almost no new listings
                if new_on_page < 5:
                    break
                if len(all_listings) >= max_listings:
                    break
                if page < max_pages:
                    time.sleep(self._delay)
            except Exception as exc:
                if page == 1:
                    result.error = str(exc)
                break
        result.listings = all_listings[:max_listings]
        result.compute_aggregates()
        if not is_etsy_html_blocked():
            time.sleep(self._delay)
        return result

    def bulk_search(
        self,
        keywords: list[str],
        max_listings: int = 20,
    ) -> list[EtsySearchResult]:
        results = []
        for kw in keywords:
            results.append(self.search(kw, max_listings=max_listings))
        return results

    def _fetch(self, keyword: str, page: int) -> str:
        if not _html_scraper_enabled():
            raise EtsyHtmlBlockedError("Etsy HTML scraper disabled by ETSY_HTML_SCRAPER_ENABLED=0")
        if is_etsy_html_blocked():
            raise EtsyHtmlBlockedError(get_etsy_html_block_reason())

        params = {"q": keyword, "explicit": "1", "page": page}
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            if attempt > 0:
                backoff = 4.0 * (2 ** (attempt - 1)) + random.uniform(0, 2)
                time.sleep(backoff)
            try:
                resp = self._client.get(
                    _SEARCH_URL,
                    params=params,
                    headers=_random_headers(),
                )
                if resp.status_code in (403, 429):
                    last_exc = RuntimeError(f"Etsy HTML returned HTTP {resp.status_code} challenge")
                    if _looks_like_challenge(resp.status_code, resp.text):
                        break
                    continue
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in (403, 429):
                    raise
            except Exception as exc:
                raise

        try:
            return _fetch_with_browser_impersonation(keyword, page)
        except Exception as exc:
            reason = f"Etsy HTML search blocked from this network ({last_exc}; {exc})"
            mark_etsy_html_blocked(reason)
            if last_exc:
                raise EtsyHtmlBlockedError(reason) from exc
            raise exc

    def close(self) -> None:
        self._client.close()


def _fetch_with_browser_impersonation(keyword: str, page: int) -> str:
    """Fallback for Etsy 403s when plain httpx gets fingerprint-blocked."""
    try:
        from curl_cffi import requests
    except Exception as exc:
        raise RuntimeError("curl-cffi is not installed for Etsy browser fallback") from exc

    resp = requests.get(
        _SEARCH_URL,
        params={"q": keyword, "explicit": "1", "page": page},
        headers=_random_headers(),
        impersonate="chrome124",
        timeout=_FALLBACK_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"browser fallback HTTP {resp.status_code}")
    return resp.text


# ── HTML parsers ──────────────────────────────────────────────────────────────

def _parse_listings(html: str, max_n: int) -> tuple[list[EtsyListingData], int]:
    """
    Try strategies in order:
    1. JSON-LD structured data (<script type="application/ld+json">)
    2. Embedded __woo_props / window.__PRELOADED_STATE__ JSON
    3. HTML regex patterns (listing cards, data attributes, price spans)
    """
    listings: list[EtsyListingData] = []
    total_count = _extract_total_count(html)

    # Strategy 1 — JSON-LD
    listings = _parse_json_ld(html, max_n)
    if listings:
        return listings, total_count

    # Strategy 2 — preloaded state JSON in <script> tags
    listings = _parse_preloaded_state(html, max_n)
    if listings:
        return listings, total_count

    # Strategy 3 — raw HTML regex on listing cards
    listings = _parse_html_regex(html, max_n)
    return listings, total_count


def _parse_json_ld(html: str, max_n: int) -> list[EtsyListingData]:
    """Extract from <script type="application/ld+json"> ItemList blocks."""
    results = []
    for blob in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(blob)
        except Exception:
            continue
        if isinstance(data, list):
            data = next((d for d in data if d.get("@type") == "ItemList"), None)
            if not data:
                continue
        if data.get("@type") != "ItemList":
            continue
        for item in data.get("itemListElement", [])[:max_n]:
            product = item.get("item", item)
            offer = product.get("offers", {})
            if isinstance(offer, list):
                offer = offer[0] if offer else {}
            price_str = offer.get("price", offer.get("lowPrice", "0"))
            try:
                price = float(str(price_str).replace(",", ""))
            except Exception:
                price = 0.0
            url = product.get("url", item.get("url", ""))
            lid = _listing_id_from_url(url)
            name = product.get("name", "")
            if lid and price > 0:
                # JSON-LD may include interactionStatistic with FavoriteAction
                fav_count = None
                for stat in product.get("interactionStatistic", []):
                    if "Favorite" in stat.get("interactionType", ""):
                        fav_count = _optional_int(stat.get("userInteractionCount"))
                results.append(EtsyListingData(
                    listing_id=lid,
                    title=name,
                    price_usd=price,
                    review_count=_optional_int(product.get("aggregateRating", {}).get("reviewCount")),
                    is_star_seller=None,
                    is_bestseller=None,
                    shop_name=_shop_from_url(url),
                    url=url,
                    num_favorites=fav_count,
                ))
        if results:
            break
    return results


def _parse_preloaded_state(html: str, max_n: int) -> list[EtsyListingData]:
    """Extract from embedded JSON state objects in <script> tags."""
    results: list[EtsyListingData] = []

    # Look for large JSON blobs containing "listing_id" keys
    for blob in re.findall(r'<script[^>]*>\s*(\{["\']listing_id["\'].*?)\s*</script>',
                           html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(blob)
            listing = _extract_one_listing(data)
            if listing:
                results.append(listing)
                if len(results) >= max_n:
                    break
        except Exception:
            continue

    if results:
        return results

    # Broader search: any script tag with lots of "listing_id" occurrences
    for blob in re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        if blob.count('"listing_id"') < 3:
            continue
        try:
            # Find all listing_id values and their surrounding context
            for m in re.finditer(r'"listing_id"\s*:\s*(\d+)', blob):
                lid = m.group(1)
                ctx = blob[max(0, m.start()-200): m.start()+500]
                price = _extract_price_from_ctx(ctx)
                title = _extract_field_from_ctx(ctx, "title")
                shop = _extract_field_from_ctx(ctx, "shop_name")
                reviews = _extract_int_field_from_ctx(ctx, "num_ratings")
                favorites = next((
                    value for value in (
                        _extract_int_field_from_ctx(ctx, "num_favorers"),
                        _extract_int_field_from_ctx(ctx, "favorited_by_count"),
                        _extract_int_field_from_ctx(ctx, "listing_favorites_count"),
                    ) if value is not None
                ), None)
                star_seller = _extract_bool_field_from_ctx(ctx, "star_seller")
                if star_seller is None:
                    star_seller = _extract_bool_field_from_ctx(ctx, "is_star_seller")
                bestseller = _extract_bool_field_from_ctx(ctx, "is_bestseller_listing")
                if lid and price > 0:
                    results.append(EtsyListingData(
                        listing_id=lid,
                        title=title,
                        price_usd=price,
                        review_count=reviews,
                        is_star_seller=star_seller,
                        is_bestseller=bestseller,
                        shop_name=shop,
                        url=f"https://www.etsy.com/listing/{lid}/",
                        num_favorites=favorites,
                    ))
                if len(results) >= max_n:
                    break
        except Exception:
            continue
        if results:
            break
    return results


def _parse_html_regex(html: str, max_n: int) -> list[EtsyListingData]:
    """Last-resort regex extraction directly from listing card HTML."""
    results: list[EtsyListingData] = []

    # Find listing IDs from data attributes
    ids = re.findall(r'data-listing-id=["\'](\d+)["\']', html)

    # Find all prices (currency-value spans)
    prices_raw = re.findall(
        r'class="[^"]*currency-value[^"]*"[^>]*>([\d,]+(?:\.\d+)?)<', html
    )
    prices = []
    for p in prices_raw:
        try:
            prices.append(float(p.replace(",", "")))
        except Exception:
            pass

    # Star sellers — count occurrences near listing cards
    star_seller_ids = set(
        re.findall(r'data-listing-id=["\'](\d+)["\'][^<]*(?:<[^>]+>)*[^<]*star.seller',
                   html, re.IGNORECASE)
    )

    for i, lid in enumerate(ids[:max_n]):
        price = prices[i] if i < len(prices) else 0.0
        if price == 0.0:
            continue
        results.append(EtsyListingData(
            listing_id=lid,
            title="",
            price_usd=price,
            review_count=None,
            is_star_seller=True if lid in star_seller_ids else None,
            is_bestseller=None,
            shop_name="",
            url=f"https://www.etsy.com/listing/{lid}/",
        ))

    return results


# ── Competition quality scorer ────────────────────────────────────────────────

# ── Utility helpers ───────────────────────────────────────────────────────────

def _extract_total_count(html: str) -> int | None:
    patterns = [
        r'"num_listings_available"\s*:\s*(\d+)',
        r'"total_count"\s*:\s*(\d+)',
        r'([\d,]+)\s+results?\s+for',
        r'"count"\s*:\s*(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except Exception:
                pass
    return None


def _listing_id_from_url(url: str) -> str:
    m = re.search(r'/listing/(\d+)', url)
    return m.group(1) if m else ""


def _shop_from_url(url: str) -> str:
    m = re.search(r'etsy\.com/shop/([^/?]+)', url)
    return m.group(1) if m else ""


def _extract_one_listing(data: dict) -> Optional[EtsyListingData]:
    lid = str(data.get("listing_id", ""))
    if not lid:
        return None
    price = _extract_price_from_ctx(json.dumps(data))
    if price <= 0:
        return None
    favorites = next((
        _optional_int(data.get(key))
        for key in ("num_favorers", "favorited_by_count", "listing_favorites_count")
        if data.get(key) is not None
    ), None)
    review_value = data.get("num_ratings")
    if review_value is None:
        review_value = data.get("num_reviews")
    return EtsyListingData(
        listing_id=lid,
        title=data.get("title", ""),
        price_usd=price,
        review_count=_optional_int(review_value),
        is_star_seller=_optional_bool(data, "is_star_seller", "star_seller"),
        is_bestseller=_optional_bool(data, "is_bestseller_listing", "is_bestseller"),
        shop_name=data.get("shop_name", ""),
        url=f"https://www.etsy.com/listing/{lid}/",
        num_favorites=favorites,
    )


def _extract_price_from_ctx(ctx: str) -> float:
    for pat in [
        r'"price"\s*:\s*"?([\d.]+)"?',
        r'"min_price"\s*:\s*"?([\d.]+)"?',
        r'"converted_price"\s*:\s*"?([\d.]+)"?',
        r'"currency_value"\s*:\s*"?([\d.]+)"?',
    ]:
        m = re.search(pat, ctx)
        if m:
            try:
                v = float(m.group(1))
                if 0.5 < v < 10000:
                    return v
            except Exception:
                pass
    return 0.0


def _extract_field_from_ctx(ctx: str, field_name: str) -> str:
    m = re.search(rf'"{field_name}"\s*:\s*"([^"]+)"', ctx)
    return m.group(1) if m else ""


def _extract_int_field_from_ctx(ctx: str, field_name: str) -> int | None:
    m = re.search(rf'"{field_name}"\s*:\s*(\d+)', ctx)
    return _optional_int(m.group(1)) if m else None


def _extract_bool_field_from_ctx(ctx: str, field_name: str) -> bool | None:
    m = re.search(rf'"{field_name}"\s*:\s*(true|false)', ctx, re.IGNORECASE)
    return m.group(1).lower() == "true" if m else None


def _optional_int(value: object) -> int | None:
    try:
        return int(str(value).replace(",", "")) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_bool(data: dict, *keys: str) -> bool | None:
    for key in keys:
        if key in data and data[key] is not None:
            return bool(data[key])
    return None
