"""
Google Trends research adapter via pytrends.
Returns trend_direction for keywords over the last 90 days.
"""

import random
import time
from adapters.base.research import BaseResearchAdapter, NicheSignal

_MAX_RETRIES = 3


class GoogleTrendsAdapter(BaseResearchAdapter):
    """Uses pytrends to get interest-over-time for keywords."""

    def __init__(self, geo: str = "US", timeframe: str = "today 3-m"):
        self._geo = geo
        self._timeframe = timeframe

    @property
    def name(self) -> str:
        return "google_trends"

    def is_configured(self) -> bool:
        try:
            import pytrends  # noqa: F401
            return True
        except ImportError:
            return False

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        return self.bulk_search([keyword])

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        if not self.is_configured():
            return []
        from pytrends.request import TrendReq

        results: list[NicheSignal] = []
        # pytrends max 5 keywords per request
        for chunk in _chunks(keywords, 5):
            for attempt in range(_MAX_RETRIES):
                try:
                    pt = TrendReq(hl="en-US", tz=360, timeout=(10, 30), retries=2, backoff_factor=0.5)
                    pt.build_payload(chunk, cat=0, timeframe=self._timeframe, geo=self._geo)
                    df = pt.interest_over_time()
                    if df.empty:
                        for kw in chunk:
                            results.append(_zero_signal(kw))
                        break
                    for kw in chunk:
                        if kw not in df.columns:
                            results.append(_zero_signal(kw))
                            continue
                        series = df[kw]
                        avg = float(series.mean())
                        recent = float(series.iloc[-4:].mean())  # last ~month
                        older = float(series.iloc[:4].mean())    # first ~month
                        trend = _trend_direction(recent, older)
                        results.append(NicheSignal(
                            keyword=kw,
                            monthly_searches=int(avg * 100),  # 0-10000 scale proxy
                            competition_score=0.0,            # not from trends
                            avg_price_usd=0.0,
                            trend_direction=trend,
                            source="google_trends",
                        ))
                    # polite delay between chunks
                    time.sleep(2.0 + random.uniform(0, 1.5))
                    break  # success — move to next chunk
                except Exception as exc:
                    err_str = str(exc).lower()
                    if "429" in err_str or "rate" in err_str or "too many" in err_str:
                        backoff = 15.0 * (2 ** attempt) + random.uniform(0, 5)
                        time.sleep(backoff)
                        if attempt == _MAX_RETRIES - 1:
                            for kw in chunk:
                                results.append(_zero_signal(kw))
                    else:
                        for kw in chunk:
                            results.append(_zero_signal(kw))
                        break
        return results


def _trend_direction(recent: float, older: float) -> str:
    if older == 0:
        return "stable"
    change = (recent - older) / older
    if change > 0.15:
        return "rising"
    if change < -0.15:
        return "declining"
    return "stable"


def _zero_signal(keyword: str) -> NicheSignal:
    return NicheSignal(
        keyword=keyword,
        monthly_searches=0,
        competition_score=0.0,
        avg_price_usd=0.0,
        trend_direction="stable",
        source="google_trends",
    )


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
