"""
Reddit integration via PRAW.
Used for niche research signal collection — surfaces community topics,
language patterns, and engagement signals from relevant subreddits.

Requires in .env:
  REDDIT_CLIENT_ID     — app client ID from reddit.com/prefs/apps
  REDDIT_CLIENT_SECRET — app client secret
  REDDIT_USER_AGENT    — any descriptive string, e.g. "etsy-pipeline/1.0"

Read-only mode only (no user credentials needed).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class RedditPost:
    post_id: str
    title: str
    subreddit: str
    score: int
    upvote_ratio: float
    num_comments: int
    created_utc: float
    url: str
    permalink: str
    selftext: str
    flair: str
    is_self: bool

    @property
    def engagement_score(self) -> float:
        import math
        return self.score * self.upvote_ratio * math.log(self.num_comments + 1 + 1)


class RedditClient:
    """Thin PRAW wrapper for read-only Reddit data collection."""

    def __init__(self) -> None:
        self._client_id     = os.getenv("REDDIT_CLIENT_ID", "")
        self._client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        self._user_agent    = os.getenv("REDDIT_USER_AGENT", "etsy-pipeline-research/1.0")

    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret
                    and not self._client_id.startswith("your_"))

    def _reddit(self):
        import praw
        return praw.Reddit(
            client_id=self._client_id,
            client_secret=self._client_secret,
            user_agent=self._user_agent,
        )

    def get_hot_posts(self, subreddit: str, limit: int = 25) -> list[RedditPost]:
        r = self._reddit()
        sub = r.subreddit(subreddit)
        return [self._to_post(s, subreddit) for s in sub.hot(limit=limit)]

    def get_top_posts(self, subreddit: str, time_filter: str = "week", limit: int = 25) -> list[RedditPost]:
        r = self._reddit()
        sub = r.subreddit(subreddit)
        return [self._to_post(s, subreddit) for s in sub.top(time_filter=time_filter, limit=limit)]

    def get_rising_posts(self, subreddit: str, limit: int = 15) -> list[RedditPost]:
        r = self._reddit()
        sub = r.subreddit(subreddit)
        return [self._to_post(s, subreddit) for s in sub.rising(limit=limit)]

    def search_subreddit(
        self,
        subreddit: str,
        query: str,
        sort: str = "relevance",
        time_filter: str = "month",
        limit: int = 15,
    ) -> list[RedditPost]:
        r = self._reddit()
        sub = r.subreddit(subreddit)
        return [self._to_post(s, subreddit) for s in sub.search(query, sort=sort, time_filter=time_filter, limit=limit)]

    def collect_niche_signals(
        self,
        subreddits: list[str],
        niche_terms: list[str],
        hot_limit: int = 20,
        top_limit: int = 15,
    ) -> list[RedditPost]:
        """Collect niche-relevant Reddit signals across multiple subreddits."""
        seen: set[str] = set()
        all_posts: list[RedditPost] = []

        for sub in subreddits:
            try:
                for p in self.get_hot_posts(sub, limit=hot_limit):
                    if p.post_id not in seen:
                        seen.add(p.post_id)
                        all_posts.append(p)
            except Exception:
                pass

            try:
                for p in self.get_top_posts(sub, time_filter="week", limit=top_limit):
                    if p.post_id not in seen:
                        seen.add(p.post_id)
                        all_posts.append(p)
            except Exception:
                pass

        if niche_terms and subreddits:
            combined_sub = "+".join(subreddits[:5])
            for term in niche_terms[:2]:
                try:
                    r = self._reddit()
                    for submission in r.subreddit(combined_sub).search(
                        term, sort="top", time_filter="month", limit=10
                    ):
                        if submission.id not in seen:
                            seen.add(submission.id)
                            all_posts.append(self._to_post(submission, submission.subreddit.display_name))
                except Exception:
                    pass

        all_posts.sort(key=lambda p: p.engagement_score, reverse=True)
        return all_posts

    def _to_post(self, submission, subreddit: str) -> RedditPost:
        return RedditPost(
            post_id=submission.id,
            title=submission.title,
            subreddit=subreddit,
            score=submission.score,
            upvote_ratio=getattr(submission, "upvote_ratio", 1.0),
            num_comments=submission.num_comments,
            created_utc=submission.created_utc,
            url=submission.url,
            permalink=f"https://reddit.com{submission.permalink}",
            selftext=(submission.selftext or "")[:500],
            flair=submission.link_flair_text or "",
            is_self=submission.is_self,
        )

    def health_check(self) -> bool:
        if not self.is_configured():
            return False
        try:
            r = self._reddit()
            next(r.subreddit("announcements").hot(limit=1))
            return True
        except Exception:
            return False
