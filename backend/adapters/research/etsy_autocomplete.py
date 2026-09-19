"""
Etsy autocomplete research adapter — no API key required.
Hits the public Etsy autocomplete endpoint to gather keyword suggestions.
"""

import httpx
from adapters.base.research import BaseResearchAdapter, NicheSignal


# Etsy changed their autocomplete endpoint — using the current suggestions API
_AUTOCOMPLETE_URL = "https://www.etsy.com/api/v3/ajax/suggest/keywords"
import random
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
]

def _get_headers():
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "DNT": "1",
        "Connection": "keep-alive",
    }


class EtsyAutocompleteAdapter(BaseResearchAdapter):
    """Collects Etsy autocomplete suggestions without inventing rank metrics."""

    def __init__(self, request_delay: float = 0.5):
        self._delay = request_delay
        self._client = httpx.Client(headers=_get_headers(), timeout=15, follow_redirects=True)

    @property
    def name(self) -> str:
        return "etsy_autocomplete"

    def is_configured(self) -> bool:
        return True  # no key needed

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        suggestions = self._get_suggestions(keyword)
        if not suggestions:
            return []
        return [self._build_signal(kw) for kw in suggestions[:10]]

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
            if resp.status_code in (404, 410):
                return []
        except Exception:
            pass
        return []

    @staticmethod
    def _build_signal(keyword: str) -> NicheSignal:
        return NicheSignal(
            keyword=keyword,
            monthly_searches=None,
            competition_score=None,
            avg_price_usd=None,
            trend_direction=None,
            source="etsy_autocomplete",
        )
