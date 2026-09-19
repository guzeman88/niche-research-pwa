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
            except Exception:
                continue
        return results

    @staticmethod
    def _parse(keyword: str, data: dict) -> NicheSignal:
        # Marmalead response shape may vary — handle both wrapped and flat
        kw_data = data.get("keyword", data)
        searches = kw_data.get("search_frequency")
        comp_raw = kw_data.get("competition")
        comp = float(comp_raw) if isinstance(comp_raw, (int, float)) else None
        avg_price_raw = kw_data.get("avg_price")
        avg_price = float(avg_price_raw) if avg_price_raw is not None else None
        return NicheSignal(
            keyword=keyword,
            monthly_searches=int(searches) if searches is not None else None,
            competition_score=comp,
            avg_price_usd=avg_price,
            trend_direction=None,
            source="marmalead",
        )
