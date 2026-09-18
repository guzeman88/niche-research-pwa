"""
eRank SEO research adapter — requires ERANK_API_KEY.
eRank provides Etsy-specific keyword data: monthly searches, competition, avg price.
Docs: https://erank.com/account/api
"""

import os
import httpx
from adapters.base.research import BaseResearchAdapter, NicheSignal


_BASE_URL = "https://api.erank.com/v2"


class ERankAdapter(BaseResearchAdapter):
    """Fetches Etsy keyword metrics from eRank API."""

    def __init__(self):
        self._api_key = os.getenv("ERANK_API_KEY", "")
        self._client = httpx.Client(timeout=20)

    @property
    def name(self) -> str:
        return "erank"

    def is_configured(self) -> bool:
        return bool(self._api_key and not self._api_key.startswith("your_"))

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        return self.bulk_search([keyword])

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        if not self.is_configured():
            return []
        results: list[NicheSignal] = []
        for kw in keywords:
            try:
                resp = self._client.get(
                    f"{_BASE_URL}/keyword",
                    params={"keyword": kw, "market": "etsy"},
                    headers={"X-Api-Key": self._api_key},
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
        searches = data.get("monthly_searches")
        comp = data.get("competition")
        avg_price = data.get("avg_price")
        trend = data.get("trend")
        return NicheSignal(
            keyword=keyword,
            monthly_searches=int(searches) if searches is not None else None,
            competition_score=min(100.0, float(comp)) if comp is not None else None,
            avg_price_usd=float(avg_price) if avg_price is not None else None,
            trend_direction=trend if trend in ("rising", "stable", "declining") else None,
            source="erank",
        )


def _zero_signal(keyword: str) -> NicheSignal:
    return NicheSignal(keyword=keyword, monthly_searches=None,
                       competition_score=None, avg_price_usd=None,
                       trend_direction=None, source="erank")
