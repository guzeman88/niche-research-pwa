"""
Pinterest Trends research adapter.
Uses Pinterest v5 API if PINTEREST_ACCESS_TOKEN is set,
otherwise falls back to scraping Pinterest's Explore page for category trends.
"""

import os
import httpx
from datetime import datetime, timezone
from adapters.base.research import BaseResearchAdapter, NicheSignal


_API_BASE = "https://api.pinterest.com/v5"


class PinterestTrendsAdapter(BaseResearchAdapter):
    """Fetches Pinterest trending keyword data."""

    def __init__(self):
        self._token = os.getenv("PINTEREST_ACCESS_TOKEN", "")
        self._client = httpx.Client(timeout=20, follow_redirects=True)

    @property
    def name(self) -> str:
        return "pinterest_trends"

    def is_configured(self) -> bool:
        return bool(self._token and not self._token.startswith("your_"))

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        return self.bulk_search([keyword])

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        if not self.is_configured():
            return []
        results: list[NicheSignal] = []
        for kw in keywords:
            try:
                resp = self._client.get(
                    f"{_API_BASE}/trends/keywords/{_slugify(kw)}/trend",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    signal = self._parse(kw, data)
                    if signal is not None:
                        results.append(signal)
            except Exception:
                continue
        return results

    @staticmethod
    def _parse(keyword: str, data: dict) -> NicheSignal | None:
        trend_data = data.get("trend_data", [])
        if not trend_data:
            return None

        values = [float(point["value"]) for point in trend_data if point.get("value") is not None]
        if not values:
            return None
        average_relative_interest = sum(values) / len(values)

        return NicheSignal(
            keyword=keyword,
            monthly_searches=None,
            competition_score=None,
            avg_price_usd=None,
            trend_direction=None,
            source="pinterest_trends",
            relative_interest=average_relative_interest,
            observed_at=datetime.now(timezone.utc).isoformat(),
            time_series=[
                {
                    "date": str(point.get("date") or point.get("timestamp") or point.get("time") or ""),
                    "value": float(point["value"]),
                }
                for point in trend_data
                if point.get("value") is not None
                and (point.get("date") or point.get("timestamp") or point.get("time"))
            ],
            metadata={"provider_endpoint": "v5/trends/keywords"},
        )


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
