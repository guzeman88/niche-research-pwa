"""Official Google Ads Keyword Planner adapter.

The adapter uses the supported Google Ads REST API.  It never drives the
Keyword Planner web UI.  Historical metrics accept as many as 10,000 keywords
per request; idea generation accepts at most 20 seed phrases per request.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from adapters.base.research import BaseResearchAdapter, NicheSignal


class GoogleAdsKeywordPlannerError(RuntimeError):
    """Raised when Google Ads authentication or collection fails."""


_REQUEST_LOCK = threading.Lock()
_TOKEN_LOCK = threading.Lock()
_last_request_at = 0.0
_cached_token: tuple[str, float] | None = None


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def is_google_ads_configured() -> bool:
    if not _env("GOOGLE_ADS_CUSTOMER_ID"):
        return False
    user_oauth = (
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
    )
    return _service_account_credentials_configured() or all(
        _usable_env(name) for name in user_oauth
    )


def _usable_env(name: str) -> bool:
    value = _env(name)
    return bool(value and not value.lower().startswith("your_"))


def _service_account_credentials_configured() -> bool:
    inline_json = _env("GOOGLE_ADS_SERVICE_ACCOUNT_JSON")
    if inline_json and not inline_json.lower().startswith("your_"):
        return True
    for name in ("GOOGLE_ADS_JSON_KEY_FILE_PATH", "GOOGLE_APPLICATION_CREDENTIALS"):
        value = _env(name)
        if value and not value.lower().startswith("your_"):
            return True
    return False


def _clean_customer_id(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


class GoogleAdsKeywordPlannerAdapter(BaseResearchAdapter):
    """Collect keyword ideas and exact historical metrics in API-sized batches."""

    MAX_HISTORICAL_KEYWORDS = 10_000
    MAX_IDEA_SEEDS = 20
    MAX_IDEA_PAGE_SIZE = 10_000

    def __init__(self, timeout: float = 90.0) -> None:
        self._timeout = timeout
        self._api_version = _env("GOOGLE_ADS_API_VERSION") or "v25"
        self._customer_id = _clean_customer_id(_env("GOOGLE_ADS_CUSTOMER_ID"))
        self._login_customer_id = _clean_customer_id(_env("GOOGLE_ADS_LOGIN_CUSTOMER_ID"))
        self._language_id = _env("GOOGLE_ADS_LANGUAGE_ID") or "1000"
        geo_ids = _env("GOOGLE_ADS_GEO_TARGET_IDS") or "2840"
        self._geo_ids = [_clean_customer_id(value) for value in geo_ids.split(",") if _clean_customer_id(value)]

    @property
    def name(self) -> str:
        return "google_ads_keyword_planner"

    def is_configured(self) -> bool:
        return is_google_ads_configured()

    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        del category
        return self.bulk_search([keyword])

    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        normalized = _normalize_keywords(keywords)
        if not normalized:
            return []
        if len(normalized) > self.MAX_HISTORICAL_KEYWORDS:
            raise ValueError(
                f"Google historical metrics accepts at most {self.MAX_HISTORICAL_KEYWORDS:,} keywords per request"
            )
        payload = self._post(
            "generateKeywordHistoricalMetrics",
            {
                "keywords": normalized,
                **self._targeting(),
                "historicalMetricsOptions": {"includeAverageCpc": True},
            },
        )
        return [self._signal_from_result(row) for row in payload.get("results", []) if isinstance(row, dict)]

    def generate_keyword_ideas(
        self,
        seed_keywords: list[str],
        *,
        max_results: int = 10_000,
    ) -> list[NicheSignal]:
        seeds = _normalize_keywords(seed_keywords)
        if not seeds:
            return []
        if len(seeds) > self.MAX_IDEA_SEEDS:
            raise ValueError(f"Google keyword ideas accepts at most {self.MAX_IDEA_SEEDS} seed keywords")

        remaining = max(1, min(int(max_results), 250_000))
        page_token: str | None = None
        signals: list[NicheSignal] = []
        while remaining > 0:
            request: dict[str, Any] = {
                "keywordSeed": {"keywords": seeds},
                "pageSize": min(self.MAX_IDEA_PAGE_SIZE, remaining),
                **self._targeting(),
                "historicalMetricsOptions": {"includeAverageCpc": True},
            }
            if page_token:
                request["pageToken"] = page_token
            payload = self._post("generateKeywordIdeas", request)
            rows = [row for row in payload.get("results", []) if isinstance(row, dict)]
            for row in rows:
                signal = self._signal_from_result(row, seed_keywords=seeds)
                if signal.keyword:
                    signals.append(signal)
            remaining -= len(rows)
            page_token = str(payload.get("nextPageToken") or "").strip() or None
            if not page_token or not rows:
                break
        return signals[:max_results]

    def _targeting(self) -> dict[str, Any]:
        return {
            "language": f"languageConstants/{self._language_id}",
            "geoTargetConstants": [f"geoTargetConstants/{value}" for value in self._geo_ids],
            "keywordPlanNetwork": "GOOGLE_SEARCH",
            "includeAdultKeywords": False,
        }

    def _post(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.is_configured():
            raise GoogleAdsKeywordPlannerError("Google Ads Keyword Planner is not configured")
        if not self._customer_id:
            raise GoogleAdsKeywordPlannerError("GOOGLE_ADS_CUSTOMER_ID must contain digits")

        url = (
            f"https://googleads.googleapis.com/{self._api_version}/customers/"
            f"{self._customer_id}:{method}"
        )
        headers = {
            "authorization": f"Bearer {_access_token(self._timeout)}",
            "content-type": "application/json",
        }
        # Developer tokens were sunset on 2026-09-09. Google still accepts and
        # ignores an existing token, so keep it as an optional compatibility
        # header for older projects while allowing new Cloud-project access.
        if _env("GOOGLE_ADS_DEVELOPER_TOKEN"):
            headers["developer-token"] = _env("GOOGLE_ADS_DEVELOPER_TOKEN")
        if self._login_customer_id:
            headers["login-customer-id"] = self._login_customer_id

        for attempt in range(3):
            _wait_for_request_slot()
            try:
                response = httpx.post(url, headers=headers, json=body, timeout=self._timeout)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise GoogleAdsKeywordPlannerError(f"Google Ads request failed: {exc}") from exc
                time.sleep(2 ** attempt)
                continue
            if response.status_code == 429 and attempt < 2:
                time.sleep(_retry_after(response, fallback=2 ** (attempt + 1)))
                continue
            if response.status_code >= 400:
                detail = _safe_error(response)
                raise GoogleAdsKeywordPlannerError(
                    f"Google Ads {method} returned HTTP {response.status_code}: {detail}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise GoogleAdsKeywordPlannerError("Google Ads returned invalid JSON") from exc
            return payload if isinstance(payload, dict) else {}
        raise GoogleAdsKeywordPlannerError("Google Ads request exhausted retry attempts")

    def _signal_from_result(
        self,
        row: dict[str, Any],
        *,
        seed_keywords: list[str] | None = None,
    ) -> NicheSignal:
        keyword = " ".join(str(row.get("text") or "").lower().split())
        metrics = row.get("keywordMetrics") or row.get("keywordIdeaMetrics") or {}
        monthly_rows = metrics.get("monthlySearchVolumes") or []
        time_series = []
        for point in monthly_rows:
            if not isinstance(point, dict):
                continue
            year = _integer(point.get("year"))
            month = _month_number(point.get("month"))
            value = _number(point.get("monthlySearches"))
            if year and month and value is not None:
                time_series.append({
                    "date": f"{year:04d}-{month:02d}-01",
                    "value": value,
                    "unit": "searches",
                    "geography": self._geography_label(),
                    "timeframe": "calendar_month",
                })
        time_series.sort(key=lambda point: point["date"])
        period_start = time_series[0]["date"] if time_series else None
        period_end = time_series[-1]["date"] if time_series else None
        competition_index = _number(metrics.get("competitionIndex"))
        metadata = {
            "competition_level": metrics.get("competition"),
            "competition_index": competition_index,
            "average_cpc_usd": _micros_to_usd(metrics.get("averageCpcMicros")),
            "low_top_of_page_bid_usd": _micros_to_usd(metrics.get("lowTopOfPageBidMicros")),
            "high_top_of_page_bid_usd": _micros_to_usd(metrics.get("highTopOfPageBidMicros")),
            "period_start": period_start,
            "period_end": period_end,
            "seed_keywords": seed_keywords or [],
            "close_variants": row.get("closeVariants") or [],
            "observations": [],
        }
        for metric, value, unit in (
            ("google_ads_competition_index", competition_index, "index_0_100"),
            ("average_cpc", metadata["average_cpc_usd"], "usd"),
            ("low_top_of_page_bid", metadata["low_top_of_page_bid_usd"], "usd"),
            ("high_top_of_page_bid", metadata["high_top_of_page_bid_usd"], "usd"),
        ):
            if value is not None:
                metadata["observations"].append({
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "period_start": period_start,
                    "period_end": period_end,
                })
        now = datetime.now(timezone.utc).isoformat()
        return NicheSignal(
            keyword=keyword,
            monthly_searches=_integer(metrics.get("avgMonthlySearches")),
            competition_score=competition_index,
            avg_price_usd=None,
            trend_direction=_trend_direction(time_series),
            source=self.name,
            relative_interest=None,
            relative_interest_period="rolling_12_months",
            observed_at=now,
            geography=self._geography_label(),
            time_series=time_series,
            metadata=metadata,
        )

    def _geography_label(self) -> str:
        if self._geo_ids == ["2840"]:
            return "US"
        return ",".join(self._geo_ids) or "ALL"


def _access_token(timeout: float) -> str:
    global _cached_token
    with _TOKEN_LOCK:
        if _cached_token and _cached_token[1] > time.monotonic() + 60:
            return _cached_token[0]
        if _service_account_credentials_configured():
            token, lifetime = _service_account_access_token(timeout)
            _cached_token = (token, time.monotonic() + lifetime)
            return token
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": _env("GOOGLE_ADS_CLIENT_ID"),
                "client_secret": _env("GOOGLE_ADS_CLIENT_SECRET"),
                "refresh_token": _env("GOOGLE_ADS_REFRESH_TOKEN"),
                "grant_type": "refresh_token",
            },
            timeout=timeout,
        )
        if response.status_code >= 400:
            raise GoogleAdsKeywordPlannerError(
                f"Google OAuth token refresh returned HTTP {response.status_code}: {_safe_error(response)}"
            )
        payload = response.json()
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise GoogleAdsKeywordPlannerError("Google OAuth response did not include an access token")
        lifetime = max(120, _integer(payload.get("expires_in")) or 3600)
        _cached_token = (token, time.monotonic() + lifetime)
        return token


def _service_account_access_token(timeout: float) -> tuple[str, int]:
    try:
        import google.auth
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - guarded by requirements
        raise GoogleAdsKeywordPlannerError(
            "google-auth is required for Google Ads service-account authentication"
        ) from exc

    scopes = ["https://www.googleapis.com/auth/adwords"]
    inline_json = _env("GOOGLE_ADS_SERVICE_ACCOUNT_JSON")
    key_path = _env("GOOGLE_ADS_JSON_KEY_FILE_PATH")
    try:
        if inline_json:
            info = json.loads(inline_json)
            if not isinstance(info, dict):
                raise ValueError("credential JSON must be an object")
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=scopes,
            )
        elif key_path:
            credentials = service_account.Credentials.from_service_account_file(
                str(Path(key_path).expanduser()),
                scopes=scopes,
            )
        else:
            credentials, _project_id = google.auth.default(scopes=scopes)
        credentials.refresh(Request())
    except Exception as exc:
        raise GoogleAdsKeywordPlannerError(
            f"Google service-account authorization failed: {exc}"
        ) from exc

    token = str(credentials.token or "").strip()
    if not token:
        raise GoogleAdsKeywordPlannerError("Google service-account credentials returned no access token")
    expiry = getattr(credentials, "expiry", None)
    if expiry is not None:
        now = datetime.now(expiry.tzinfo or timezone.utc)
        lifetime = max(120, int((expiry - now).total_seconds()))
    else:
        lifetime = 3600
    return token, lifetime


def _wait_for_request_slot() -> None:
    global _last_request_at
    with _REQUEST_LOCK:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        _last_request_at = time.monotonic()


def _normalize_keywords(values: list[str]) -> list[str]:
    return list(dict.fromkeys(" ".join(str(value).lower().split()) for value in values if str(value).strip()))


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _micros_to_usd(value: Any) -> float | None:
    number = _number(value)
    return round(number / 1_000_000, 6) if number is not None else None


def _month_number(value: Any) -> int | None:
    if isinstance(value, int) and 1 <= value <= 12:
        return value
    text = str(value or "").upper()
    names = (
        "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
        "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
    )
    return names.index(text) + 1 if text in names else None


def _trend_direction(points: list[dict[str, Any]]) -> str | None:
    if len(points) < 2:
        return None
    first = float(points[0]["value"])
    last = float(points[-1]["value"])
    if first <= 0:
        return "rising" if last > 0 else "stable"
    change = (last - first) / first
    if change >= 0.10:
        return "rising"
    if change <= -0.10:
        return "declining"
    return "stable"


def _retry_after(response: httpx.Response, *, fallback: float) -> float:
    try:
        return max(1.0, float(response.headers.get("retry-after", fallback)))
    except (TypeError, ValueError):
        return fallback


def _safe_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("status") or "request rejected")[:500]
    except ValueError:
        pass
    return "request rejected"
