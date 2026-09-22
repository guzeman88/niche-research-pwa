"""Optional eRank private-API adapter.

eRank does not document a generally available public API. EtGen therefore has
no built-in eRank endpoint. The adapter is enabled only when a provider-issued
endpoint and key are both supplied; ordinary eRank data should use the CSV/TSV
evidence importer instead.
"""

import os
import httpx
from adapters.base.research import BaseResearchAdapter, NicheSignal


class ERankAdapter(BaseResearchAdapter):
    """Fetch Etsy keyword metrics from an explicitly granted private API."""

    def __init__(self):
        self._api_key = os.getenv("ERANK_API_KEY", "")
        self._api_url = os.getenv("ERANK_API_URL", "").strip().rstrip("/")
        self._client = httpx.Client(timeout=20)

    @property
    def name(self) -> str:
        return "erank"

    def is_configured(self) -> bool:
        return bool(
            self._api_url.startswith("https://")
            and self._api_key
            and not self._api_key.startswith("your_")
        )

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        return self.bulk_search([keyword])

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        if not self.is_configured():
            return []
        results: list[NicheSignal] = []
        for kw in keywords:
            try:
                resp = self._client.get(
                    self._api_url,
                    params={"keyword": kw, "market": "etsy"},
                    headers={"X-Api-Key": self._api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results.append(self._parse(kw, data))
            except Exception:
                continue
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
            competition_score=float(comp) if comp is not None else None,
            avg_price_usd=float(avg_price) if avg_price is not None else None,
            trend_direction=trend if trend in ("rising", "stable", "declining") else None,
            source="erank",
        )
