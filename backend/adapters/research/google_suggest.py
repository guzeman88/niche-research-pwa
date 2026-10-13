"""
Google Suggest research adapter — free, unblocked keyword discovery.
Returns real search queries from Google's suggest API (shopping focus).
Replaces the broken Etsy autocomplete adapter.
"""
from __future__ import annotations

import json, time, random, os
from contextlib import nullcontext
from datetime import datetime, timezone
from datetime import timedelta
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
        self.keyword_outcomes = {}

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
                metadata={"surface": "shopping_suggest", "language": "en", "parent_keyword": keyword,
                          "capture_status": self.keyword_outcomes.get(keyword, 'completed')},
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
        from services.collection_transport import transport
        shared = transport('suggest')
        with nullcontext(shared) if shared is not None else httpx.Client(timeout=8) as client:
            return self._records(keyword, client)

    def _records(self, keyword, client):
        suggestions: list[dict] = []
        prefixes = ["", "etsy ", "custom ", "personalized "]
        successful = 0

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
                r = client.get(_SUGGEST_URL, params=params, headers=headers, timeout=8)
                r.raise_for_status()
                if r.status_code == 200:
                    data = json.loads(r.text.replace("window.google.ac.h(", "").rstrip(")")) if "google.ac.h" in r.text else json.loads(r.text)
                    if not isinstance(data, list) or len(data) < 2:
                        raise ValueError('InvalidSuggestResponse')
                    items = data[1]
                    if not isinstance(items, list):
                        raise ValueError('InvalidSuggestResponse')
                    successful += 1
                    for position, s in enumerate(items, start=1):
                        if isinstance(s, str):
                            clean = s.replace("etsy ", "").strip().lower()
                            if clean and clean != keyword.lower() and len(clean) > 3:
                                suggestions.append({
                                    "query": query.lower(),
                                    "suggestion": clean,
                                    "position": position,
                                })
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {429, 503}:
                    if os.environ.get('FEED_MAX_COLLECTION') == '1':
                        from pipeline import keyword_database as db
                        from email.utils import parsedate_to_datetime
                        retry = exc.response.headers.get('retry-after', '900')
                        try:
                            seconds = max(900, float(retry))
                        except ValueError:
                            try:
                                seconds = max(900, (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds())
                            except (ValueError, TypeError):
                                seconds = 900
                        due = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
                        with db._conn() as con:
                            con.execute('INSERT OR REPLACE INTO feed_provider_cooldowns VALUES(?,?,?,?,?)',
                                        ('google_suggest', '__provider__', 0, 1, due))
                    break
                continue
            except Exception:
                continue
            finally:
                time.sleep(self._delay)

        if successful < len(prefixes) and not suggestions:
            self.keyword_outcomes[keyword] = 'failed'
            raise RuntimeError('SuggestIncompleteResponse')
        self.keyword_outcomes[keyword] = 'completed' if successful == len(prefixes) else 'partial'

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
