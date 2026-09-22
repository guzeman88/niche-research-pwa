"""Optional Marmalead private-API adapter.

Marmalead does not document a generally available public API. EtGen therefore
does not guess an endpoint. Automatic collection is enabled only when the
provider has issued both an endpoint and a key; normal exports belong in the
structured evidence importer.
"""

import os
import httpx
from adapters.base.research import BaseResearchAdapter, NicheSignal


class MarmaleadAdapter(BaseResearchAdapter):
    """Fetch Etsy keyword data from an explicitly granted private API."""

    def __init__(self):
        self._api_key = os.getenv("MARMALEAD_API_KEY", "")
        self._api_url = os.getenv("MARMALEAD_API_URL", "").strip().rstrip("/")
        self._client = httpx.Client(timeout=20)

    @property
    def name(self) -> str:
        return "marmalead"

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
