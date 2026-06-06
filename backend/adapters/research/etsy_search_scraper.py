"""
Etsy Search Scraper — no API key required.
Scrapes Etsy search results pages to extract real listing data:
  - Prices (full distribution, not just average)
  - Review counts (proxy for sales volume)
  - Star Seller / Bestseller badges (competition quality)
  - Shop names, listing titles, listing IDs

Revenue estimation heuristic (same as Alura/EverBee):
  estimated_sales = review_count × 20   (assumes ~5% review rate)
  monthly_revenue = (estimated_sales / listing_age_months) × price

Competition quality score (0-100, higher = harder to break into):
  - Average review count of top 20     (0-40 pts)
  - % Star Sellers in top 20           (0-30 pts)
  - % Bestseller badges                (0-20 pts)
  - Price coherence (tight = mature)   (0-10 pts)
"""

from __future__ import annotations

import json
import math
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
_MAX_RETRIES  = 3      # retry on 403/429 with backoff


@dataclass
class EtsyListingData:
    listing_id: str
    title: str
    price_usd: float
    review_count: int
    is_star_seller: bool
    is_bestseller: bool
    shop_name: str
    url: str
    num_favorites: int = 0       # people who favorited — direct buyer-intent signal
    # Computed
    estimated_lifetime_sales: int = 0
    estimated_monthly_revenue_usd: float = 0.0

    def __post_init__(self):
        # 5% review rate → multiply reviews by 20 for estimated sales
        self.estimated_lifetime_sales = self.review_count * 20
        # Assume average listing is ~18 months old
        self.estimated_monthly_revenue_usd = round(
            (self.review_count * 20 / 18) * self.price_usd, 2
        )


@dataclass
class PriceDistribution:
    min: float = 0.0
    p25: float = 0.0
    median: float = 0.0
    p75: float = 0.0
    max: float = 0.0
    mean: float = 0.0
    sweet_spot: str = ""   # e.g. "$12–$28 (middle 50%)"

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
    total_listing_count: int
    listings: list[EtsyListingData] = field(default_factory=list)
    price_distribution: PriceDistribution = field(default_factory=PriceDistribution)
    # Aggregate metrics
    avg_review_count: float = 0.0
    pct_star_sellers: float = 0.0
    pct_bestsellers: float = 0.0
    competition_quality_score: float = 0.0   # 0-100
    estimated_total_monthly_revenue_usd: float = 0.0
    avg_favorites: float = 0.0          # avg favorites across sampled listings
    max_favorites: int = 0              # single highest-favorited listing
    pct_high_favorites: float = 0.0     # % listings with ≥100 favorites
    error: str = ""

    def compute_aggregates(self) -> None:
        if not self.listings:
            return
        n = len(self.listings)
        prices = [l.price_usd for l in self.listings if l.price_usd > 0]
        if prices:
            self.price_distribution = PriceDistribution.from_prices(prices)
        self.avg_review_count = round(
            sum(l.review_count for l in self.listings) / n, 1
        )
        self.pct_star_sellers = round(
            sum(1 for l in self.listings if l.is_star_seller) / n * 100, 1
        )
        self.pct_bestsellers = round(
            sum(1 for l in self.listings if l.is_bestseller) / n * 100, 1
        )
        self.estimated_total_monthly_revenue_usd = round(
            sum(l.estimated_monthly_revenue_usd for l in self.listings), 2
        )
        favs = [l.num_favorites for l in self.listings if l.num_favorites > 0]
        if favs:
            self.avg_favorites = round(sum(favs) / len(favs), 1)
            self.max_favorites = max(favs)
            self.pct_high_favorites = round(sum(1 for f in favs if f >= 100) / n * 100, 1)
        self.competition_quality_score = _score_competition(self)


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
        result = EtsySearchResult(keyword=keyword, total_listing_count=0)
        try:
            html = self._fetch(keyword, page)
            listings, total_count = _parse_listings(html, max_listings)
            result.total_listing_count = total_count
            result.listings = listings
            result.compute_aggregates()
        except Exception as exc:
            result.error = str(exc)
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
        result = EtsySearchResult(keyword=keyword, total_listing_count=0)
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
                    last_exc = httpx.HTTPStatusError(
                        f"Client error '{resp.status_code}' for url '{resp.url}'",
                        request=resp.request, response=resp,
                    )
                    continue
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in (403, 429):
                    raise
            except Exception as exc:
                raise
        raise last_exc


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
                fav_count = 0
                for stat in product.get("interactionStatistic", []):
                    if "Favorite" in stat.get("interactionType", ""):
                        try:
                            fav_count = int(stat.get("userInteractionCount", 0))
                        except Exception:
                            pass
                results.append(EtsyListingData(
                    listing_id=lid,
                    title=name,
                    price_usd=price,
                    review_count=int(product.get("aggregateRating", {}).get("reviewCount", 0)),
                    is_star_seller=False,
                    is_bestseller=False,
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
                favorites = (
                    _extract_int_field_from_ctx(ctx, "num_favorers")
                    or _extract_int_field_from_ctx(ctx, "favorited_by_count")
                    or _extract_int_field_from_ctx(ctx, "listing_favorites_count")
                )
                star_seller = '"star_seller":true' in ctx or '"is_star_seller":true' in ctx
                bestseller = '"is_bestseller_listing":true' in ctx
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
            review_count=0,
            is_star_seller=lid in star_seller_ids,
            is_bestseller=False,
            shop_name="",
            url=f"https://www.etsy.com/listing/{lid}/",
        ))

    return results


# ── Competition quality scorer ────────────────────────────────────────────────

def _score_competition(result: EtsySearchResult) -> float:
    """
    Score 0–100: how hard it is to compete in this niche based on top listing data.
    Higher score = more established competition = harder to break in.

    Components:
      avg_review_count (0-40 pts): <10 reviews avg → easy, >200 → very hard
      pct_star_sellers (0-30 pts): % of Star Sellers in top 20
      pct_bestsellers  (0-20 pts): % of Bestseller badges
      listing_count    (0-10 pts): total search results (log scale)
    """
    # Review count score — log scale
    avg_rev = result.avg_review_count
    if avg_rev <= 5:
        rev_pts = 5.0
    elif avg_rev <= 20:
        rev_pts = 10.0
    elif avg_rev <= 50:
        rev_pts = 18.0
    elif avg_rev <= 150:
        rev_pts = 28.0
    elif avg_rev <= 500:
        rev_pts = 36.0
    else:
        rev_pts = 40.0

    star_pts = min(30.0, result.pct_star_sellers * 0.30)
    best_pts = min(20.0, result.pct_bestsellers * 0.20)

    # Listing count — log scale capped
    if result.total_listing_count > 0:
        cnt_pts = min(10.0, math.log10(result.total_listing_count) / math.log10(500_000) * 10)
    else:
        cnt_pts = 5.0

    return round(rev_pts + star_pts + best_pts + cnt_pts, 1)


# ── Utility helpers ───────────────────────────────────────────────────────────

def _extract_total_count(html: str) -> int:
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
    return 0


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
    favorites = int(
        data.get("num_favorers")
        or data.get("favorited_by_count")
        or data.get("listing_favorites_count")
        or 0
    )
    return EtsyListingData(
        listing_id=lid,
        title=data.get("title", ""),
        price_usd=price,
        review_count=int(data.get("num_ratings", data.get("num_reviews", 0)) or 0),
        is_star_seller=bool(data.get("is_star_seller") or data.get("star_seller")),
        is_bestseller=bool(data.get("is_bestseller_listing") or data.get("is_bestseller")),
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


def _extract_int_field_from_ctx(ctx: str, field_name: str) -> int:
    m = re.search(rf'"{field_name}"\s*:\s*(\d+)', ctx)
    try:
        return int(m.group(1)) if m else 0
    except Exception:
        return 0
