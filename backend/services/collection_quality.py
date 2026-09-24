"""Measured collection coverage by provider.

Percentages in this module always have an observed numerator and denominator.
When a provider does not expose capacity, is approval-gated, or has no recent
run, the result is ``None`` (shown as TBD by the client).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pipeline import keyword_database as kdb
from services.provider_telemetry import get_provider_events, get_provider_states


TARGET_MIN_PCT = 80
TARGET_MAX_PCT = 100

_SOURCES = (
    ("etsy_open_api", "quota_utilization", "Etsy listings, prices, shops, and competition"),
    ("google_suggest", "eligible_keyword_coverage", "Buyer phrasing and long-tail discovery"),
    ("google_trends", "eligible_keyword_coverage", "Relative demand history and related queries"),
    ("google_daily_trends", "feed_coverage", "Current breakout search topics"),
    ("pinterest_trends", "feed_coverage", "Visual product trends after API approval"),
    ("reddit_etsy", "eligible_keyword_coverage", "Customer language and unmet needs after API approval"),
    ("etsy_marketplace_insights", "import_row_coverage", "Imported first-party Etsy keyword metrics"),
    ("etsy_shop_stats", "import_row_coverage", "Imported own-shop visits, orders, and revenue"),
    ("google_keyword_planner", "import_row_coverage", "Imported Google demand and bid ranges"),
    ("erank", "import_row_coverage", "Imported Etsy search, click, and competition metrics"),
    ("marmalead", "import_row_coverage", "Imported keyword engagement and competition metrics"),
    ("google_trends_csv", "import_row_coverage", "Imported dated Google Trends series"),
)


def _pct(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(max(0.0, min(100.0, float(numerator) / float(denominator) * 100)), 1)


def _target_status(value: float | None, configured: bool | None) -> str:
    if configured is False:
        return "not_configured"
    if value is None:
        return "tbd"
    return "on_target" if TARGET_MIN_PCT <= value <= TARGET_MAX_PCT else "below_target"


def _event_totals(events: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    for event in events:
        provider = str(event.get("provider") or "")
        if not provider:
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        row = totals.setdefault(provider, {
            "eligible": 0,
            "processed": 0,
            "usable": 0,
            "provider_rows": 0,
            "covered_rows": 0,
            "new_rows": 0,
        })
        eligible = metadata.get("eligible_keywords")
        processed = metadata.get("processed_keywords")
        usable = metadata.get("usable_keywords")
        if isinstance(eligible, (int, float)):
            row["eligible"] += max(0, int(eligible))
        if isinstance(processed, (int, float)):
            row["processed"] += max(0, int(processed))
        if isinstance(usable, (int, float)):
            row["usable"] += max(0, int(usable))
        for source_key, target_key in (
            ("provider_rows", "provider_rows"),
            ("covered_rows", "covered_rows"),
            ("new_rows", "new_rows"),
        ):
            value = metadata.get(source_key)
            if isinstance(value, (int, float)):
                row[target_key] += max(0, int(value))
    return totals


def get_collection_quality(*, hours: int = 24) -> dict[str, Any]:
    """Return measured rates for the requested rolling window."""
    kdb.init_db()
    states = get_provider_states()
    events = get_provider_events(hours=hours)
    totals = _event_totals(events)
    rows = []
    for provider, metric, purpose in _SOURCES:
        state = states.get(provider, {})
        configured = state.get("configured") if state else None
        provider_totals = totals.get(provider, {})
        numerator: int | float | None = None
        denominator: int | float | None = None
        yield_pct: float | None = None

        if metric == "quota_utilization":
            rate_limit = state.get("rate_limit") if isinstance(state.get("rate_limit"), dict) else {}
            limit = rate_limit.get("limit_per_day")
            remaining = rate_limit.get("remaining_today")
            processed = int(provider_totals.get("processed", 0))
            if (
                isinstance(limit, (int, float)) and limit > 0
                and isinstance(remaining, (int, float))
            ):
                denominator = int(limit)
                numerator = max(0, min(int(limit), int(limit) - int(remaining)))
            elif isinstance(limit, (int, float)) and limit > 0 and processed > 0:
                denominator = int(limit)
                numerator = processed
        elif metric == "eligible_keyword_coverage":
            local = kdb.get_provider_keyword_coverage(provider, hours=hours)
            event_eligible = int(provider_totals.get("eligible", 0))
            event_processed = int(provider_totals.get("processed", 0))
            if event_eligible > 0:
                denominator = event_eligible
                numerator = event_processed
                yield_pct = _pct(provider_totals.get("usable", 0), event_processed)
            elif local["attempted"] > 0:
                denominator = local["attempted"]
                numerator = local["completed"]
                yield_pct = _pct(local["with_data"], local["completed"])
        elif metric in {"feed_coverage", "import_row_coverage"}:
            provider_rows = int(provider_totals.get("provider_rows", 0))
            if provider_rows > 0:
                denominator = provider_rows
                numerator = int(provider_totals.get("covered_rows", 0))

        rate_pct = _pct(numerator, denominator)
        rows.append({
            "source": provider,
            "metric": metric,
            "purpose": purpose,
            "configured": configured,
            "status": state.get("status") if state else None,
            "collection_rate_pct": rate_pct,
            "quality_yield_pct": yield_pct,
            "collected": numerator,
            "eligible_or_available": denominator,
            "new_rows": provider_totals.get("new_rows") if provider_totals else None,
            "target_status": _target_status(rate_pct, configured),
            "last_attempt_at": state.get("last_attempt_at") if state else None,
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": max(1, int(hours)),
        "target_min_pct": TARGET_MIN_PCT,
        "target_max_pct": TARGET_MAX_PCT,
        "sources": rows,
    }
