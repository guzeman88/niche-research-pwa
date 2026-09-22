"""
Google Trends research adapter via pytrends.
Returns the observed average relative-interest index for the requested period.
"""

import random
import threading
import time
from datetime import datetime, timezone
from adapters.base.research import BaseResearchAdapter, NicheSignal

_MAX_RETRIES = 3
_PREFETCH_LOCK = threading.Lock()
_PREFETCHED: dict[tuple[str, str, str], NicheSignal | None] = {}


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
        cached: list[NicheSignal] = []
        missing: list[str] = []
        with _PREFETCH_LOCK:
            for keyword in keywords:
                key = self._cache_key(keyword)
                if key not in _PREFETCHED:
                    missing.append(keyword)
                    continue
                signal = _PREFETCHED.pop(key)
                if signal is not None:
                    cached.append(signal)
        return cached + (self._fetch(missing) if missing else [])

    def prefetch(self, keywords: list[str]) -> int:
        """Fetch a scheduler batch once, then serve each keyword from memory."""
        requested = [keyword for keyword in keywords if keyword.strip()]
        if not requested:
            return 0
        signals = self._fetch(requested)
        by_keyword = {self._cache_key(signal.keyword): signal for signal in signals}
        with _PREFETCH_LOCK:
            for keyword in requested:
                key = self._cache_key(keyword)
                # Cache provider-confirmed no-data results too, otherwise the
                # individual scan would immediately repeat the same request.
                _PREFETCHED[key] = by_keyword.get(key)
        return len(signals)

    def _cache_key(self, keyword: str) -> tuple[str, str, str]:
        return (self._geo, self._timeframe, " ".join(keyword.lower().split()))

    def _fetch(self, keywords: list[str]) -> list[NicheSignal]:
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
                    related = _related_queries(pt)
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
                            metadata={
                                "category": 0,
                                "language": "en-US",
                                "related_queries": related.get(kw, []),
                            },
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


def _related_queries(client) -> dict[str, list[str]]:
    """Preserve provider-returned related phrases from the current payload."""
    try:
        payload = client.related_queries()
    except Exception:
        return {}
    result: dict[str, list[str]] = {}
    for keyword, groups in (payload or {}).items():
        values: list[str] = []
        if not isinstance(groups, dict):
            continue
        for group_name in ("rising", "top"):
            frame = groups.get(group_name)
            if frame is None or getattr(frame, "empty", True) or "query" not in frame.columns:
                continue
            for value in frame["query"].tolist():
                phrase = " ".join(str(value).lower().split())
                if phrase and phrase not in values:
                    values.append(phrase)
        result[str(keyword)] = values
    return result
