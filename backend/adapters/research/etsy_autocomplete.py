"""
Etsy autocomplete research adapter — no API key required.
Hits the public Etsy autocomplete endpoint to gather keyword suggestions
and estimates competition/demand from listing count queries.
"""

import time
import httpx
from adapters.base.research import BaseResearchAdapter, NicheSignal


_AUTOCOMPLETE_URL = "https://www.etsy.com/api/v3/ajax/autocomplete/etsy_search"
_SEARCH_URL = "https://www.etsy.com/search"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


class EtsyAutocompleteAdapter(BaseResearchAdapter):
    """Scrapes Etsy autocomplete + listing counts for demand/competition signals."""

    def __init__(self, request_delay: float = 0.5):
        self._delay = request_delay
        self._client = httpx.Client(headers=_HEADERS, timeout=15, follow_redirects=True)

    @property
    def name(self) -> str:
        return "etsy_autocomplete"

    def is_configured(self) -> bool:
        return True  # no key needed

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        suggestions = self._get_suggestions(keyword)
        results: list[NicheSignal] = []
        for kw in suggestions[:10]:
            count = self._get_listing_count(kw)
            results.append(self._build_signal(kw, count))
            time.sleep(self._delay)
        return results

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        results: list[NicheSignal] = []
        for kw in keywords:
            results.extend(self.search(kw))
        return results

    # ── private ───────────────────────────────────────────────────────────────

    def _get_suggestions(self, keyword: str) -> list[str]:
        try:
            resp = self._client.get(
                _AUTOCOMPLETE_URL,
                params={"query": keyword, "limit": 20, "include_metadata": "true"},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                # response can be list of strings or list of dicts
                if results and isinstance(results[0], dict):
                    return [r.get("query", r.get("term", "")) for r in results if r.get("query") or r.get("term")]
                return [r for r in results if isinstance(r, str)]
        except Exception:
            pass
        # fallback: keyword itself as sole candidate
        return [keyword]

    def _get_listing_count(self, keyword: str) -> int:
        """Returns approximate listing count from Etsy search page."""
        try:
            resp = self._client.get(
                _SEARCH_URL,
                params={"q": keyword, "explicit": "1"},
            )
            if resp.status_code == 200:
                text = resp.text
                # look for "X,XXX results" or "X results"
                import re
                m = re.search(r'"num_listings_available":(\d+)', text)
                if m:
                    return int(m.group(1))
                m = re.search(r'([\d,]+)\s+results', text)
                if m:
                    return int(m.group(1).replace(",", ""))
        except Exception:
            pass
        return 0

    @staticmethod
    def _build_signal(keyword: str, listing_count: int) -> NicheSignal:
        # competition score: log-scale capped at 100
        # <5k listings = low competition; >500k = very high
        import math
        if listing_count <= 0:
            comp = 50.0
        else:
            comp = min(100.0, math.log10(max(1, listing_count)) / math.log10(500_000) * 100)

        # demand score inversely related to competition (autocomplete proxy)
        demand_proxy = max(0, 100 - comp * 0.6)

        # trend: no trend data from this source — default stable
        return NicheSignal(
            keyword=keyword,
            monthly_searches=int(demand_proxy * 100),  # rough proxy
            competition_score=round(comp, 1),
            avg_price_usd=0.0,  # not available from autocomplete
            trend_direction="stable",
            source="etsy_autocomplete",
        )
