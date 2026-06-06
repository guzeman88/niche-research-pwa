"""
Marmalead SEO research adapter — requires MARMALEAD_API_KEY.
Marmalead provides Etsy keyword engagement, search frequency, and competition.
Docs: https://marmalead.com/api
"""

import os
import httpx
from adapters.base.research import BaseResearchAdapter, NicheSignal


_BASE_URL = "https://api.marmalead.com/v1"


class MarmaleadAdapter(BaseResearchAdapter):
    """Fetches Etsy keyword data from Marmalead API."""

    def __init__(self):
        self._api_key = os.getenv("MARMALEAD_API_KEY", "")
        self._client = httpx.Client(timeout=20)

    @property
    def name(self) -> str:
        return "marmalead"

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
                    f"{_BASE_URL}/keywords",
                    params={"q": kw},
                    headers={"Authorization": f"Bearer {self._api_key}"},
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
        # Marmalead response shape may vary — handle both wrapped and flat
        kw_data = data.get("keyword", data)
        searches = int(kw_data.get("search_frequency", 0) or 0)
        comp_raw = kw_data.get("competition", 50)
        comp = float(comp_raw) if isinstance(comp_raw, (int, float)) else 50.0
        avg_price = float(kw_data.get("avg_price", 0) or 0)
        engagement = kw_data.get("engagement", "medium") or "medium"
        trend = {"high": "rising", "medium": "stable", "low": "declining"}.get(
            str(engagement).lower(), "stable"
        )
        return NicheSignal(
            keyword=keyword,
            monthly_searches=searches,
            competition_score=min(100.0, comp),
            avg_price_usd=avg_price,
            trend_direction=trend,
            source="marmalead",
        )


def _zero_signal(keyword: str) -> NicheSignal:
    return NicheSignal(keyword=keyword, monthly_searches=0,
                       competition_score=50.0, avg_price_usd=0.0,
                       trend_direction="stable", source="marmalead")
