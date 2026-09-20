"""
Official Etsy Open API adapter.

Uses Etsy's v3 API when credentials are available. This is the stable path for
real Etsy listing evidence; HTML scraping remains an optional fallback only.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

from adapters.base.research import BaseResearchAdapter, NicheSignal
from adapters.research.etsy_search_scraper import (
    EtsyListingData,
    EtsySearchResult,
)
from adapters.research.etsy_listing_scraper import ListingDetail

_BASE_URL = os.getenv("ETSY_OPEN_API_BASE_URL", "https://api.etsy.com/v3/application")


def _api_key_header() -> str:
    explicit = os.getenv("ETSY_X_API_KEY", "").strip()
    if explicit:
        return explicit

    keystring = (
        os.getenv("ETSY_API_KEYSTRING", "").strip()
        or os.getenv("ETSY_API_KEY", "").strip()
    )
    shared_secret = (
        os.getenv("ETSY_SHARED_SECRET", "").strip()
        or os.getenv("ETSY_API_SHARED_SECRET", "").strip()
    )
    if keystring and shared_secret:
        return f"{keystring}:{shared_secret}"
    return keystring


def is_etsy_open_api_configured() -> bool:
    key = _api_key_header()
    return bool(key and not key.lower().startswith("your_"))


class EtsyOpenAPIError(RuntimeError):
    """Raised when Etsy Open API credentials or requests fail."""


class EtsyOpenAPIClient:
    def __init__(self, timeout: float = 20.0):
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)

    def is_configured(self) -> bool:
        return is_etsy_open_api_configured()

    def close(self) -> None:
        self._client.close()

    def search_listings(self, keyword: str, limit: int = 50) -> EtsySearchResult:
        if not self.is_configured():
            raise EtsyOpenAPIError("Etsy Open API is not configured")

        payload = self._get(
            "/listings/active",
            params={
                "keywords": keyword,
                "limit": max(1, min(int(limit), 100)),
                "offset": 0,
                "sort_on": "score",
                "sort_order": "down",
            },
        )
        rows = _extract_results(payload)
        result = EtsySearchResult(
            keyword=keyword,
            total_listing_count=_extract_count(payload),
        )
        result.listings = [
            listing
            for row in rows
            if (listing := _listing_data_from_api(row)) is not None
        ]
        result.compute_aggregates()
        return result

    def fetch_listing(self, listing_id: str) -> ListingDetail:
        if not self.is_configured():
            raise EtsyOpenAPIError("Etsy Open API is not configured")
        payload = self._get(f"/listings/{listing_id}")
        row = _extract_single(payload)
        return _listing_detail_from_api(str(listing_id), row)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"x-api-key": _api_key_header(), "accept": "application/json"}
        oauth_token = os.getenv("ETSY_OAUTH_TOKEN", "").strip()
        if oauth_token:
            headers["authorization"] = f"Bearer {oauth_token}"

        resp = self._client.get(f"{_BASE_URL}{path}", params=params, headers=headers)
        if resp.status_code == 401:
            raise EtsyOpenAPIError("Etsy Open API rejected credentials (401)")
        if resp.status_code == 403:
            raise EtsyOpenAPIError("Etsy Open API credentials are not authorized for this endpoint (403)")
        if resp.status_code == 429:
            raise EtsyOpenAPIError("Etsy Open API rate limit hit (429)")
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception as exc:
            raise EtsyOpenAPIError("Etsy Open API returned a non-JSON response") from exc
        if not isinstance(data, dict):
            raise EtsyOpenAPIError("Etsy Open API returned an unexpected response shape")
        return data


class EtsyOpenAPIAdapter(BaseResearchAdapter):
    """Market signals from the official Etsy listings endpoint."""

    def __init__(self):
        self._client = EtsyOpenAPIClient()

    @property
    def name(self) -> str:
        return "etsy_open_api"

    def is_configured(self) -> bool:
        return self._client.is_configured()

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        if not self.is_configured():
            return []
        result = self._client.search_listings(keyword, limit=50)
        prices = [
            item.price_usd for item in result.listings
            if item.price_usd > 0 and item.currency_code == "USD"
        ]
        avg_price = sum(prices) / len(prices) if prices else None
        return [
            NicheSignal(
                keyword=keyword,
                monthly_searches=None,
                competition_score=None,
                avg_price_usd=round(avg_price, 2) if avg_price is not None else None,
                trend_direction=None,
                source=self.name,
            )
        ]

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        signals: list[NicheSignal] = []
        for keyword in keywords:
            try:
                signals.extend(self.search(keyword))
            except Exception:
                continue
        return signals


def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results", [])
    if isinstance(results, list):
        return [row for row in results if isinstance(row, dict)]
    return []


def _extract_single(payload: dict[str, Any]) -> dict[str, Any]:
    if "results" in payload:
        rows = _extract_results(payload)
        return rows[0] if rows else {}
    return payload


def _extract_count(payload: dict[str, Any]) -> int | None:
    for key in ("count", "total_count", "total"):
        raw_value = payload.get(key)
        if raw_value is None:
            continue
        try:
            value = int(raw_value)
            if value >= 0:
                return value
        except Exception:
            pass
    return None


def _listing_data_from_api(row: dict[str, Any]) -> EtsyListingData | None:
    listing_id = str(row.get("listing_id") or "").strip()
    price = _money_to_float(row.get("price") or row.get("price_usd"))
    if not listing_id or price is None or price <= 0:
        return None
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or f"https://www.etsy.com/listing/{listing_id}/")
    return EtsyListingData(
        listing_id=listing_id,
        title=title,
        price_usd=price,
        review_count=None,
        is_star_seller=None,
        is_bestseller=None,
        shop_name=_shop_name(row),
        url=url,
        num_favorites=_first_int(row, "num_favorers", "favorers"),
        currency_code=_money_currency(row.get("price") or row.get("price_usd")),
    )


def _listing_detail_from_api(listing_id: str, row: dict[str, Any]) -> ListingDetail:
    detail = ListingDetail(
        listing_id=listing_id,
        title=str(row.get("title") or ""),
        tags=_clean_tags(row.get("tags") or row.get("materials") or []),
        shop_name=_shop_name(row),
        price_usd=_money_to_float(row.get("price") or row.get("price_usd")),
        num_favorites=_first_int(row, "num_favorers", "favorers"),
        url=str(row.get("url") or f"https://www.etsy.com/listing/{listing_id}/"),
    )
    created = _timestamp_value(
        row.get("original_creation_timestamp")
        or row.get("created_timestamp")
        or row.get("creation_tsz")
    )
    if created:
        detail.listed_date = created.date()
        detail.listing_age_months = round(max(0, (datetime.utcnow().date() - detail.listed_date).days) / 30.4375, 1)
    return detail


def _money_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace("$", "").replace(",", "").strip())
        except Exception:
            return None
    if isinstance(value, dict):
        amount = value.get("amount")
        divisor = value.get("divisor")
        if amount is not None and divisor is not None:
            try:
                return round(float(amount) / float(divisor), 2)
            except Exception:
                return None
    return None


def _money_currency(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    currency = str(value.get("currency_code") or value.get("currency") or "").strip().upper()
    return currency or None


def _shop_name(row: dict[str, Any]) -> str:
    shop = row.get("shop")
    if isinstance(shop, dict):
        return str(shop.get("shop_name") or shop.get("name") or "")
    return str(row.get("shop_name") or row.get("shop_id") or "")


def _clean_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        parts = [str(part).strip() for part in value]
    else:
        parts = []
    seen: set[str] = set()
    tags: list[str] = []
    for part in parts:
        tag = part.lower()
        if not tag or tag in seen or len(tag) > 50:
            continue
        seen.add(tag)
        tags.append(tag)
        if len(tags) >= 13:
            break
    return tags


def _timestamp_value(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.utcfromtimestamp(int(value))
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _int_value(value: Any) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except Exception:
        return None


def _first_int(row: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key in row and row[key] is not None:
            return _int_value(row[key])
    return None
