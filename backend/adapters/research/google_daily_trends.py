"""Google Daily Search Trends RSS adapter.

The public feed reports currently trending queries and an approximate traffic
floor such as ``20K+``.  That number is deliberately stored as a lower-bound
observation, never as exact or monthly search volume.
"""

from __future__ import annotations

import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from adapters.base.research import BaseResearchAdapter, NicheSignal


_FEED_URL = "https://trends.google.com/trending/rss"
_HT = "{https://trends.google.com/trending/rss}"
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class GoogleDailyTrendsAdapter(BaseResearchAdapter):
    """Collect the public, country-specific Google trending-search feed."""

    def __init__(self):
        self._geo = os.getenv("GOOGLE_DAILY_TRENDS_GEO", "US").strip().upper() or "US"
        self._cache_seconds = max(
            300,
            int(os.getenv("GOOGLE_DAILY_TRENDS_CACHE_SECONDS", "3600")),
        )
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    @property
    def name(self) -> str:
        return "google_daily_trends"

    def is_configured(self) -> bool:
        return True

    def discovery_interval_seconds(self) -> int:
        """Use the configured provider-feed cache interval as the polling cadence."""
        return self._cache_seconds

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        del category
        return self.bulk_search([keyword])

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        requested = {_normalize(keyword) for keyword in keywords if keyword.strip()}
        return [
            self._parse(row, position)
            for position, row in enumerate(self._fetch_trends(), start=1)
            if _normalize(str(row.get("keyword") or "")) in requested
        ]

    def discover(self) -> list[NicheSignal]:
        return [
            self._parse(row, position)
            for position, row in enumerate(self._fetch_trends(), start=1)
        ]

    def _fetch_trends(self) -> list[dict[str, Any]]:
        with _CACHE_LOCK:
            cached = _CACHE.get(self._geo)
            if cached and time.monotonic() - cached[0] < self._cache_seconds:
                return cached[1]

        response = self._client.get(_FEED_URL, params={"geo": self._geo})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        rows: list[dict[str, Any]] = []
        for item in root.findall("./channel/item"):
            keyword = _text(item, "title")
            if not keyword:
                continue
            traffic_display = _text(item, f"{_HT}approx_traffic")
            traffic_floor, is_lower_bound = _parse_traffic(traffic_display)
            rows.append({
                "keyword": keyword,
                "published_at": _parse_published_at(_text(item, "pubDate")),
                "provider_url": _text(item, "link") or f"{_FEED_URL}?geo={self._geo}",
                "approx_traffic_display": traffic_display or None,
                "approx_traffic_floor": traffic_floor,
                "traffic_is_lower_bound": is_lower_bound,
                "picture_url": _text(item, f"{_HT}picture") or None,
                "picture_source": _text(item, f"{_HT}picture_source") or None,
                "news_items": [_parse_news(news) for news in item.findall(f"{_HT}news_item")],
            })

        with _CACHE_LOCK:
            _CACHE[self._geo] = (time.monotonic(), rows)
        return rows

    def _parse(self, data: dict[str, Any], position: int) -> NicheSignal:
        traffic_floor = data.get("approx_traffic_floor")
        observations = []
        if traffic_floor is not None:
            observations.append({
                "metric": "approx_search_traffic_lower_bound",
                "value": traffic_floor,
                "unit": "searches_lower_bound",
            })
        return NicheSignal(
            keyword=_normalize(str(data.get("keyword") or "")),
            monthly_searches=None,
            competition_score=None,
            avg_price_usd=None,
            trend_direction=None,
            source=self.name,
            observed_at=data.get("published_at"),
            geography=self._geo,
            position=position,
            metadata={
                "provider_url": data.get("provider_url"),
                "rank": position,
                "approx_traffic_display": data.get("approx_traffic_display"),
                "traffic_is_lower_bound": data.get("traffic_is_lower_bound"),
                "picture_url": data.get("picture_url"),
                "picture_source": data.get("picture_source"),
                "news_items": data.get("news_items") or [],
                "observations": observations,
            },
        )


def _text(element: ET.Element, path: str) -> str:
    child = element.find(path)
    return (child.text or "").strip() if child is not None else ""


def _parse_news(element: ET.Element) -> dict[str, str | None]:
    return {
        "title": _text(element, f"{_HT}news_item_title") or None,
        "snippet": _text(element, f"{_HT}news_item_snippet") or None,
        "url": _text(element, f"{_HT}news_item_url") or None,
        "picture_url": _text(element, f"{_HT}news_item_picture") or None,
        "source": _text(element, f"{_HT}news_item_source") or None,
    }


def _parse_published_at(value: str) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_traffic(value: str) -> tuple[int | None, bool | None]:
    display = value.strip().upper().replace(",", "")
    if not display:
        return None, None
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB])?\s*(\+)?", display)
    if not match:
        return None, None
    multiplier = {None: 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2)]
    return int(float(match.group(1)) * multiplier), bool(match.group(3))


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())
