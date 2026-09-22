"""Pinterest Trends API adapter using the documented v5 endpoint.

Pinterest returns a ranked set of current trends for a region; it does not
offer arbitrary keyword lookup through this endpoint. ``bulk_search`` therefore
returns evidence only when an exact requested keyword appears in that set.
``discover`` exposes the complete returned trend set for scheduled discovery.
"""

from __future__ import annotations

import base64
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from adapters.base.research import BaseResearchAdapter, NicheSignal


_API_BASE = "https://api.pinterest.com/v5"
_CACHE_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str, int], tuple[float, list[dict[str, Any]]]] = {}


class PinterestTrendsAdapter(BaseResearchAdapter):
    """Collect current Pinterest trends after Pinterest app approval."""

    def __init__(self):
        self._token = os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()
        self._refresh_token = os.getenv("PINTEREST_REFRESH_TOKEN", "").strip()
        self._app_id = os.getenv("PINTEREST_APP_ID", "").strip()
        self._app_secret = os.getenv("PINTEREST_APP_SECRET", "").strip()
        self._region = os.getenv("PINTEREST_TRENDS_REGION", "US").strip().upper() or "US"
        self._trend_type = os.getenv("PINTEREST_TREND_TYPE", "growing").strip().lower() or "growing"
        self._limit = min(50, max(1, int(os.getenv("PINTEREST_TRENDS_LIMIT", "50"))))
        self._cache_seconds = max(300, int(os.getenv("PINTEREST_TRENDS_CACHE_SECONDS", "21600")))
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    @property
    def name(self) -> str:
        return "pinterest_trends"

    def is_configured(self) -> bool:
        return bool(self._token and not self._token.startswith("your_"))

    def discovery_interval_seconds(self) -> int:
        """Use the configured provider cache interval as the polling cadence."""
        return self._cache_seconds

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        return self.bulk_search([keyword])

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        if not self.is_configured():
            return []
        requested = {_normalize(keyword) for keyword in keywords if keyword.strip()}
        return [
            self._parse(row, position)
            for position, row in enumerate(self._fetch_trends(), start=1)
            if _normalize(str(row.get("keyword") or "")) in requested
        ]

    def discover(self) -> list[NicheSignal]:
        """Return every currently ranked trend supplied by Pinterest."""
        if not self.is_configured():
            return []
        return [self._parse(row, position) for position, row in enumerate(self._fetch_trends(), start=1)]

    def _fetch_trends(self) -> list[dict[str, Any]]:
        cache_key = (self._region, self._trend_type, self._limit)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < self._cache_seconds:
                return cached[1]

        url = f"{_API_BASE}/trends/keywords/{self._region}/top/{self._trend_type}"
        response = self._client.get(
            url,
            params={"limit": self._limit},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if response.status_code == 401 and self._can_refresh():
            self._refresh_access_token()
            response = self._client.get(
                url,
                params={"limit": self._limit},
                headers={"Authorization": f"Bearer {self._token}"},
            )
        response.raise_for_status()
        payload = response.json()
        trends = payload.get("trends") if isinstance(payload, dict) else None
        rows = [row for row in (trends or []) if isinstance(row, dict) and row.get("keyword")]
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), rows)
        return rows

    def _can_refresh(self) -> bool:
        return bool(self._refresh_token and self._app_id and self._app_secret)

    def _refresh_access_token(self) -> None:
        encoded = base64.b64encode(f"{self._app_id}:{self._app_secret}".encode()).decode()
        response = self._client.post(
            f"{_API_BASE}/oauth/token",
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise RuntimeError("Pinterest refresh response did not contain an access token")
        self._token = token
        next_refresh = str(payload.get("refresh_token") or "").strip()
        if next_refresh:
            self._refresh_token = next_refresh

    def _parse(self, data: dict[str, Any], position: int) -> NicheSignal:
        keyword = str(data.get("keyword") or "").strip().lower()
        raw_series = data.get("time_series")
        if isinstance(raw_series, dict):
            points = [
                {"date": str(date), "value": float(value), "unit": "relative_interest_index"}
                for date, value in sorted(raw_series.items())
                if _number(value) is not None
            ]
        elif isinstance(raw_series, list):
            points = [
                {
                    "date": str(point.get("date") or point.get("timestamp") or point.get("time")),
                    "value": float(point["value"]),
                    "unit": "relative_interest_index",
                }
                for point in raw_series
                if isinstance(point, dict)
                and _number(point.get("value")) is not None
                and (point.get("date") or point.get("timestamp") or point.get("time"))
            ]
        else:
            points = []

        values = [point["value"] for point in points]
        observations = []
        for field, metric in (
            ("pct_growth_wow", "growth_week_over_week"),
            ("pct_growth_mom", "growth_month_over_month"),
            ("pct_growth_yoy", "growth_year_over_year"),
        ):
            value = _number(data.get(field))
            if value is not None:
                observations.append({"metric": metric, "value": value, "unit": "percent"})

        return NicheSignal(
            keyword=keyword,
            monthly_searches=None,
            competition_score=None,
            avg_price_usd=None,
            trend_direction=None,
            source="pinterest_trends",
            relative_interest=(sum(values) / len(values)) if values else None,
            relative_interest_period="weekly_past_year",
            observed_at=datetime.now(timezone.utc).isoformat(),
            geography=self._region,
            position=position,
            time_series=points,
            metadata={
                "provider_endpoint": "v5/trends/keywords/{region}/top/{trend_type}",
                "trend_type": self._trend_type,
                "rank": position,
                "series_normalization": "independent_0_100",
                "observations": observations,
            },
        )


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
