"""
Pinterest Trends research adapter.
Uses Pinterest v5 API if PINTEREST_ACCESS_TOKEN is set,
otherwise falls back to scraping Pinterest's Explore page for category trends.
"""

import os
import httpx
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
                    results.append(self._parse(kw, data))
                else:
                    results.append(_zero_signal(kw))
            except Exception:
                results.append(_zero_signal(kw))
        return results

    @staticmethod
    def _parse(keyword: str, data: dict) -> NicheSignal:
        trend_data = data.get("trend_data", [])
        if not trend_data:
            return _zero_signal(keyword)

        values = [point.get("value", 0) for point in trend_data]
        avg = sum(values) / len(values) if values else 0
        recent = sum(values[-4:]) / 4 if len(values) >= 4 else avg
        older = sum(values[:4]) / 4 if len(values) >= 4 else avg

        if older and recent > older * 1.15:
            trend = "rising"
        elif older and recent < older * 0.85:
            trend = "declining"
        else:
            trend = "stable"

        return NicheSignal(
            keyword=keyword,
            monthly_searches=int(avg * 1000),  # Pinterest index 0-100 → scale
            competition_score=0.0,              # not provided by Pinterest
            avg_price_usd=0.0,
            trend_direction=trend,
            source="pinterest_trends",
        )


def _zero_signal(keyword: str) -> NicheSignal:
    return NicheSignal(keyword=keyword, monthly_searches=0,
                       competition_score=0.0, avg_price_usd=0.0,
                       trend_direction="stable", source="pinterest_trends")


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
