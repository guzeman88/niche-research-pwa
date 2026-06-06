"""
Etsy Listing Page Scraper — no API key required.

Fetches individual listing pages to extract data unavailable from search results:
  - All 13 seller-defined tags (exact keywords they optimized for)
  - Listing creation date (for real age-adjusted revenue, not the 18-month assumption)
  - Exact favorite count
  - Shop name + total shop sales + active listing count

This data powers 4 of the 6 gap detection signals:
  tag_gap      — buyer search terms that no seller tags for
  style_gap    — dominant tag cluster (existing aesthetic = a gap for alternatives)
  recency_gap  — average listing age vs. buyer demand freshness
  quality_gap  — shop maturity signals (sales velocity, listing count)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_LISTING_URL = "https://www.etsy.com/listing/{listing_id}"
_SHOP_URL = "https://www.etsy.com/shop/{shop_name}"
_REQUEST_DELAY = 1.5


@dataclass
class ListingDetail:
    listing_id: str
    title: str = ""
    tags: list[str] = field(default_factory=list)           # up to 13 seller tags
    listed_date: Optional[date] = None                      # exact listing creation date
    listing_age_months: float = 18.0                        # computed from listed_date
    shop_name: str = ""
    price_usd: float = 0.0
    num_favorites: int = 0
    num_reviews: int = 0
    url: str = ""
    error: str = ""


@dataclass
class ShopDetail:
    shop_name: str
    total_sales: int = 0
    active_listing_count: int = 0
    shop_age_months: float = 0.0
    sales_velocity: float = 0.0      # sales per month
    revenue_per_listing: float = 0.0
    error: str = ""


class EtsyListingScraper:
    """
    Scrapes individual Etsy listing pages for tag and age data.
    Rate-limited identically to the search scraper.
    """

    def __init__(self, request_delay: float = _REQUEST_DELAY):
        self._delay = request_delay
        self._client = httpx.Client(
            headers=_HEADERS, timeout=25, follow_redirects=True
        )

    def fetch_listing(self, listing_id: str) -> ListingDetail:
        """Fetch a single listing page and extract all available signals."""
        detail = ListingDetail(
            listing_id=listing_id,
            url=_LISTING_URL.format(listing_id=listing_id),
        )
        try:
            resp = self._client.get(detail.url)
            resp.raise_for_status()
            html = resp.text
            _populate_listing_detail(detail, html)
        except Exception as exc:
            detail.error = str(exc)
        time.sleep(self._delay)
        return detail

    def fetch_listings_bulk(
        self,
        listing_ids: list[str],
        max_listings: int = 15,
    ) -> list[ListingDetail]:
        """
        Fetch multiple listing pages. Caps at max_listings to stay polite.
        Returns results in same order as input IDs (errors included).
        """
        results = []
        for lid in listing_ids[:max_listings]:
            results.append(self.fetch_listing(lid))
        return results

    def fetch_shop(self, shop_name: str) -> ShopDetail:
        """Fetch shop page to get total sales + listing count."""
        detail = ShopDetail(shop_name=shop_name)
        try:
            resp = self._client.get(_SHOP_URL.format(shop_name=shop_name))
            resp.raise_for_status()
            html = resp.text
            _populate_shop_detail(detail, html)
        except Exception as exc:
            detail.error = str(exc)
        time.sleep(self._delay)
        return detail

    def close(self) -> None:
        self._client.close()


# ── Listing page parsers ──────────────────────────────────────────────────────

def _populate_listing_detail(detail: ListingDetail, html: str) -> None:
    """Fill in detail fields from listing page HTML. Tries multiple strategies."""
    # Strategy 1: JSON-LD Product block
    if _parse_listing_json_ld(detail, html):
        pass  # tags may still be missing, try embedded state too
    # Strategy 2: embedded preloaded state / window.__woo / data attributes
    _parse_listing_preloaded_state(detail, html)
    # Strategy 3: raw HTML regex patterns as fallback
    if not detail.tags:
        _parse_listing_html_tags(detail, html)
    # Extract "Listed on" date from HTML text (visible on page, not in JSON)
    if detail.listed_date is None:
        _extract_listed_date(detail, html)
    # Compute age from date
    if detail.listed_date:
        delta = date.today() - detail.listed_date
        detail.listing_age_months = max(0.1, round(delta.days / 30.44, 1))
    # Clean up tags
    detail.tags = _clean_tags(detail.tags)


def _parse_listing_json_ld(detail: ListingDetail, html: str) -> bool:
    """Extract from <script type="application/ld+json"> Product block."""
    found_anything = False
    for blob in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(blob)
        except Exception:
            continue
        if isinstance(data, list):
            data = next((d for d in data if d.get("@type") in ("Product", "IndividualProduct")), None)
            if not data:
                continue
        if data.get("@type") not in ("Product", "IndividualProduct"):
            continue

        if not detail.title:
            detail.title = data.get("name", "")
        if not detail.shop_name:
            detail.shop_name = _shop_from_url(data.get("url", ""))

        # Keywords field = seller tags in JSON-LD
        kw_raw = data.get("keywords", "")
        if isinstance(kw_raw, str) and kw_raw:
            detail.tags = [t.strip() for t in kw_raw.split(",") if t.strip()]
            found_anything = True
        elif isinstance(kw_raw, list) and kw_raw:
            detail.tags = [str(t).strip() for t in kw_raw if str(t).strip()]
            found_anything = True

        # Price
        if detail.price_usd == 0.0:
            offer = data.get("offers", {})
            if isinstance(offer, list):
                offer = offer[0] if offer else {}
            price_str = offer.get("price", offer.get("lowPrice", "0"))
            try:
                detail.price_usd = float(str(price_str).replace(",", ""))
            except Exception:
                pass

        # Reviews
        if detail.num_reviews == 0:
            try:
                detail.num_reviews = int(
                    data.get("aggregateRating", {}).get("reviewCount", 0)
                )
            except Exception:
                pass

        if found_anything:
            break
    return found_anything


def _parse_listing_preloaded_state(detail: ListingDetail, html: str) -> None:
    """Extract from embedded JSON state in <script> tags."""
    # Look for tags array in JSON blobs
    tag_patterns = [
        r'"tags"\s*:\s*\[([^\]]+)\]',
        r'"listing_tags"\s*:\s*\[([^\]]+)\]',
        r'"keyword"\s*:\s*\[([^\]]+)\]',
    ]

    for pat in tag_patterns:
        m = re.search(pat, html)
        if m:
            raw = m.group(1)
            tags = re.findall(r'"([^"]+)"', raw)
            if tags and not detail.tags:
                detail.tags = tags
                break

    # listing_id context — search for a JSON block that has both listing_id and tags
    for blob in re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        if '"listing_id"' not in blob and '"tags"' not in blob:
            continue
        if len(blob) < 100:
            continue
        try:
            # Find the "tags" array closest to a listing_id
            m = re.search(r'"tags"\s*:\s*\[([^\]]*)\]', blob)
            if m:
                tags = re.findall(r'"([^"]+)"', m.group(1))
                if tags and len(tags) > 1 and not detail.tags:
                    detail.tags = tags

            # favorites
            if detail.num_favorites == 0:
                for fav_field in ["num_favorers", "favorited_by_count", "listing_favorites_count"]:
                    fav_m = re.search(rf'"{fav_field}"\s*:\s*(\d+)', blob)
                    if fav_m:
                        detail.num_favorites = int(fav_m.group(1))
                        break

            # shop name
            if not detail.shop_name:
                sn = re.search(r'"shop_name"\s*:\s*"([^"]+)"', blob)
                if sn:
                    detail.shop_name = sn.group(1)

            # price
            if detail.price_usd == 0.0:
                for price_field in ["price", "converted_price", "min_price"]:
                    pm = re.search(rf'"{price_field}"\s*:\s*"?([\d.]+)"?', blob)
                    if pm:
                        try:
                            v = float(pm.group(1))
                            if 0.5 < v < 10000:
                                detail.price_usd = v
                                break
                        except Exception:
                            pass

            # title
            if not detail.title:
                tm = re.search(r'"title"\s*:\s*"([^"]+)"', blob)
                if tm:
                    detail.title = tm.group(1)

            if detail.tags:
                break
        except Exception:
            continue


def _parse_listing_html_tags(detail: ListingDetail, html: str) -> None:
    """Last-resort: look for tag links in the page HTML."""
    # Etsy renders tags as links in the listing description area
    # Pattern: <a href="/search?q=tag">tag text</a> inside a tags section
    tags_section = re.search(
        r'(?:Tags|tag-list)[^<]*(?:<[^>]+>)+(.{20,2000}?)(?:</ul>|</div>)',
        html, re.DOTALL | re.IGNORECASE,
    )
    if tags_section:
        found = re.findall(r'<a[^>]+>([^<]+)</a>', tags_section.group(1))
        detail.tags = [t.strip() for t in found if len(t.strip()) > 1][:13]

    # Also try data-tag attributes
    if not detail.tags:
        data_tags = re.findall(r'data-tag=["\']([^"\']+)["\']', html)
        detail.tags = data_tags[:13]


def _extract_listed_date(detail: ListingDetail, html: str) -> None:
    """
    Extract the listing creation date from visible page text.
    Etsy shows "Listed on [Month DD, YYYY]" on the listing page.
    """
    patterns = [
        r'[Ll]isted\s+on\s+([A-Za-z]+ \d{1,2},?\s*\d{4})',
        r'"listing_creation_tsz"\s*:\s*(\d{10})',   # Unix timestamp
        r'"original_creation_tsz"\s*:\s*(\d{10})',
        r'"created_timestamp"\s*:\s*(\d{10})',
        r'"listingDate"\s*:\s*"([^"]+)"',
        r'"dateCreated"\s*:\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if not m:
            continue
        raw = m.group(1).strip()
        # Unix timestamp
        if raw.isdigit() and len(raw) == 10:
            try:
                detail.listed_date = datetime.utcfromtimestamp(int(raw)).date()
                return
            except Exception:
                continue
        # ISO date string
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%B %d, %Y", "%B %d %Y"):
            try:
                detail.listed_date = datetime.strptime(raw[:19], fmt).date()
                return
            except Exception:
                continue


# ── Shop page parsers ─────────────────────────────────────────────────────────

def _populate_shop_detail(detail: ShopDetail, html: str) -> None:
    """Fill in shop metrics from shop page HTML."""
    # Total sales — shown prominently on shop pages
    sales_patterns = [
        r'"transaction_sold_count"\s*:\s*(\d+)',
        r'"num_favorers"\s*:\s*(\d+)',  # not sales but a signal
        r'([\d,]+)\s+[Ss]ales?',
        r'"sales_count"\s*:\s*(\d+)',
        r'"shop_sales_count"\s*:\s*(\d+)',
    ]
    for pat in sales_patterns:
        m = re.search(pat, html)
        if m:
            try:
                detail.total_sales = int(m.group(1).replace(",", ""))
                break
            except Exception:
                pass

    # Active listing count
    listing_patterns = [
        r'"listing_count"\s*:\s*(\d+)',
        r'"active_listings_count"\s*:\s*(\d+)',
        r'([\d,]+)\s+[Ll]istings?',
    ]
    for pat in listing_patterns:
        m = re.search(pat, html)
        if m:
            try:
                detail.active_listing_count = int(m.group(1).replace(",", ""))
                break
            except Exception:
                pass

    # Shop creation date → age in months
    date_patterns = [
        r'"create_date"\s*:\s*(\d{10})',
        r'"join_date"\s*:\s*(\d{10})',
        r'"creation_tsz"\s*:\s*(\d{10})',
    ]
    for pat in date_patterns:
        m = re.search(pat, html)
        if m:
            try:
                created = datetime.utcfromtimestamp(int(m.group(1)))
                delta_months = (datetime.utcnow() - created).days / 30.44
                detail.shop_age_months = round(max(1, delta_months), 1)
                break
            except Exception:
                pass

    # Derived metrics
    if detail.shop_age_months > 0:
        detail.sales_velocity = round(detail.total_sales / detail.shop_age_months, 1)
    if detail.active_listing_count > 0:
        detail.revenue_per_listing = round(detail.total_sales / detail.active_listing_count, 1)


# ── Utility helpers ───────────────────────────────────────────────────────────

def _shop_from_url(url: str) -> str:
    m = re.search(r'etsy\.com/shop/([^/?]+)', url)
    return m.group(1) if m else ""


def _clean_tags(tags: list[str]) -> list[str]:
    """Normalize and deduplicate tags, keep at most 13 (Etsy's max)."""
    seen = set()
    clean = []
    for tag in tags:
        t = tag.strip().lower()
        # Skip obvious non-tag strings (long sentences, URLs, etc.)
        if not t or len(t) > 50 or t in seen or "/" in t or t.startswith("http"):
            continue
        seen.add(t)
        clean.append(t)
        if len(clean) >= 13:
            break
    return clean
