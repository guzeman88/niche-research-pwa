"""
Google Suggest research adapter — free, unblocked keyword discovery.
Returns real search queries from Google's suggest API (shopping focus).
Replaces the broken Etsy autocomplete adapter.
"""
from __future__ import annotations

import json, time, random
from datetime import datetime, timezone
import httpx
from adapters.base.research import BaseResearchAdapter, NicheSignal

_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
]

class GoogleSuggestAdapter(BaseResearchAdapter):
    """Uses Google Suggest API to discover real keyword variations."""

    def __init__(self, request_delay: float = 0.3):
        self._delay = request_delay

    @property
    def name(self) -> str:
        return "google_suggest"

    def is_configured(self) -> bool:
        return True  # no key needed

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        suggestions = self._get_suggestion_records(keyword)
        results = []
        observed_at = datetime.now(timezone.utc).isoformat()
        for record in suggestions:
            results.append(NicheSignal(
                keyword=record["suggestion"],
                monthly_searches=None,
                competition_score=None,
                avg_price_usd=None,
                trend_direction=None,
                source="google_suggest",
                observed_at=observed_at,
                geography="US",
                query=record["query"],
                position=record["position"],
                metadata={"surface": "shopping_suggest", "language": "en"},
            ))
        return results

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        results = []
        for kw in keywords:
            results.extend(self.search(kw))
        return results

    def _get_suggestions(self, keyword: str) -> list[str]:
        """Fetch Google Suggest completions for a keyword."""
        return [record["suggestion"] for record in self._get_suggestion_records(keyword)]

    def _get_suggestion_records(self, keyword: str) -> list[dict]:
        """Fetch suggestions with the exact query and provider-returned position."""
        suggestions: list[dict] = []
        prefixes = ["", "etsy ", "custom ", "personalized "]

        for prefix in prefixes:
            try:
                query = (prefix + keyword).strip()
                params = {
                    "client": "chrome",
                    "q": query,
                    "hl": "en",
                    "gl": "us",
                    "ds": "sh",  # shopping focus
                }
                headers = {
                    "User-Agent": random.choice(_USER_AGENTS),
                    "Accept": "application/json",
                }
                r = httpx.get(_SUGGEST_URL, params=params, headers=headers, timeout=8)
                if r.status_code == 200:
                    data = json.loads(r.text.replace("window.google.ac.h(", "").rstrip(")")) if "google.ac.h" in r.text else json.loads(r.text)
                    items = data[1] if isinstance(data, list) and len(data) > 1 else []
                    for position, s in enumerate(items, start=1):
                        if isinstance(s, str):
                            clean = s.replace("etsy ", "").strip().lower()
                            if clean and clean != keyword.lower() and len(clean) > 3:
                                suggestions.append({
                                    "query": query.lower(),
                                    "suggestion": clean,
                                    "position": position,
                                })
                time.sleep(self._delay)
            except Exception:
                continue

        # Dedup and limit
        # The same phrase often appears for several prefix queries.  Preserve
        # its first provider position, but do not store duplicate evidence just
        # because a second query surface returned it too.
        seen: set[str] = set()
        unique = []
        for record in suggestions:
            key = record["suggestion"]
            if key not in seen:
                seen.add(key)
                unique.append(record)
        return unique
