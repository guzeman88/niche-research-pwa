"""
Google Trends research adapter via pytrends.
Returns the observed average relative-interest index for the requested period.
"""

import random
import time
from datetime import datetime, timezone
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
                    pt = TrendReq(hl="en-US", tz=360, timeout=(10, 30))
                    pt.build_payload(chunk, cat=0, timeframe=self._timeframe, geo=self._geo)
                    df = pt.interest_over_time()
                    if df.empty:
                        break
                    for kw in chunk:
                        if kw not in df.columns:
                            continue
                        series = df[kw]
                        avg = float(series.mean())
                        points = [
                            {
                                "date": timestamp.isoformat(),
                                "value": float(value),
                                "is_partial": bool(df.loc[timestamp].get("isPartial", False)),
                            }
                            for timestamp, value in series.items()
                        ]
                        results.append(NicheSignal(
                            keyword=kw,
                            monthly_searches=None,
                            competition_score=None,
                            avg_price_usd=None,
                            trend_direction=None,
                            source="google_trends",
                            relative_interest=avg,
                            relative_interest_period=self._timeframe,
                            observed_at=datetime.now(timezone.utc).isoformat(),
                            geography=self._geo or "worldwide",
                            time_series=points,
                            metadata={"category": 0, "language": "en-US"},
                        ))
                    # polite delay between chunks
                    time.sleep(2.0 + random.uniform(0, 1.5))
                    break  # success — move to next chunk
                except Exception as exc:
                    err_str = str(exc).lower()
                    if "429" in err_str or "rate" in err_str or "too many" in err_str:
                        backoff = 15.0 * (2 ** attempt) + random.uniform(0, 5)
                        time.sleep(backoff)
                    else:
                        break
        return results


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
