"""
Reddit research adapter for Etsy/POD niche signals.
Thin wrapper over integrations/reddit.py targeting Etsy-relevant subreddits.
"""

import os
from dataclasses import asdict
from datetime import datetime, timezone
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
                posts = []
                seen: set[str] = set()
                for subreddit in self._subreddits:
                    for post in client.search_subreddit(
                        subreddit=subreddit,
                        query=kw,
                        sort="relevance",
                        time_filter="month",
                        limit=10,
                    ):
                        if post.post_id not in seen:
                            seen.add(post.post_id)
                            posts.append(post)
                if not posts:
                    continue
                results.append(NicheSignal(
                    keyword=kw,
                    monthly_searches=None,
                    competition_score=None,
                    avg_price_usd=None,
                    trend_direction=None,
                    source="reddit_etsy",
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    metadata={
                        "query": kw,
                        "time_filter": "month",
                        "subreddits": self._subreddits,
                        "observations": [
                            {"metric": "posts_returned", "value": len(posts), "unit": "count"},
                            {"metric": "post_score_total", "value": sum(post.score for post in posts), "unit": "count"},
                            {"metric": "comment_count_total", "value": sum(post.num_comments for post in posts), "unit": "count"},
                        ],
                        "posts": [asdict(post) for post in posts],
                    },
                ))
            except Exception:
                pass
        return results

    def _get_client(self):
        if self._client is None:
            from adapters.integrations.reddit import RedditClient
            self._client = RedditClient()
        return self._client
