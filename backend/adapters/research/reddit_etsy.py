"""
Reddit research adapter for Etsy/POD niche signals.
Thin wrapper over integrations/reddit.py targeting Etsy-relevant subreddits.
"""

import os
from adapters.base.research import BaseResearchAdapter, NicheSignal


_DEFAULT_SUBREDDITS = [
    "Etsy",
    "EtsySellers",
    "printondemand",
    "craftsnark",
    "smallbusiness",
]


class RedditEtsyAdapter(BaseResearchAdapter):
    """Searches Reddit for trending product/niche discussions."""

    def __init__(self, subreddits: list[str] | None = None):
        self._subreddits = subreddits or _DEFAULT_SUBREDDITS
        self._client = None

    @property
    def name(self) -> str:
        return "reddit_etsy"

    def is_configured(self) -> bool:
        return bool(
            os.getenv("REDDIT_CLIENT_ID")
            and os.getenv("REDDIT_CLIENT_SECRET")
        )

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        return self.bulk_search([keyword])

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        if not self.is_configured():
            return []
        client = self._get_client()
        results: list[NicheSignal] = []
        for kw in keywords:
            try:
                posts = client.collect_niche_signals(
                    keyword=kw,
                    subreddits=self._subreddits,
                    limit=25,
                )
                if not posts:
                    continue
                # aggregate: upvote avg as demand proxy, comment count as engagement
                avg_score = sum(p.score for p in posts) / len(posts)
                avg_comments = sum(p.num_comments for p in posts) / len(posts)
                demand = min(100.0, avg_score / 10)  # rough scale
                results.append(NicheSignal(
                    keyword=kw,
                    monthly_searches=int(avg_score),
                    competition_score=min(100.0, avg_comments * 2),
                    avg_price_usd=0.0,
                    trend_direction=_trend_from_posts(posts),
                    source="reddit_etsy",
                ))
            except Exception:
                pass
        return results

    def _get_client(self):
        if self._client is None:
            from adapters.integrations.reddit import RedditClient
            self._client = RedditClient()
        return self._client


def _trend_from_posts(posts) -> str:
    if not posts:
        return "stable"
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).timestamp()
    recent = [p for p in posts if (now - p.created_utc) < 86400 * 30]
    if len(recent) >= len(posts) * 0.6:
        return "rising"
    if len(recent) <= len(posts) * 0.2:
        return "declining"
    return "stable"
