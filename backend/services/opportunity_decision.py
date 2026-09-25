"""Versioned, auditable pre-launch decisions built from exact evidence.

This model is deliberately a decision aid, not a revenue forecast. It will not
combine demand and supply from different providers or fill missing economics
with defaults. The returned evidence snapshot and fingerprint make every score
reproducible after the underlying collectors continue to run.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any


MODEL_VERSION = "etgen-decision-v1.0.0"
MIN_LISTING_SAMPLE = 10
MAX_MARKET_EVIDENCE_AGE_DAYS = 180

DEMAND_METRICS = (
    "searches",
    "searches_30d",
    "current_period_searches",
    "monthly_searches",
)
SUPPLY_METRICS = ("listing_count", "competition_listings")


def evaluate_opportunity(
    evidence: dict[str, Any],
    product_type: str,
    *,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a transparent pre-launch decision for one keyword/product pair."""
    now = evaluated_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    keyword = str(evidence.get("keyword") or "").strip().lower()
    normalized_product = _normalize_product_type(product_type)
    blockers: list[str] = []
    cautions: list[str] = []

    market_pair = _latest_market_pair(evidence.get("observations") or [])
    economics = _latest_economics(
        evidence.get("product_economics") or [], normalized_product
    )
    sample_count = _listing_sample_count(evidence)
    trend = _trend_summary(evidence.get("trend_points") or [])
    outcome_count = len(evidence.get("outcomes") or [])

    if not market_pair:
        blockers.append(
            "Record demand and competing-listing counts from the same source and reporting period."
        )
    if not economics:
        blockers.append(
            f"Record exact unit economics for {normalized_product.replace('_', ' ')}."
        )
    if sample_count < MIN_LISTING_SAMPLE:
        blockers.append(
            f"Collect at least {MIN_LISTING_SAMPLE} marketplace listing samples; {sample_count} are recorded."
        )

    evidence_age_days = None
    if market_pair:
        evidence_age_days = _age_days(market_pair["observed_at"], now)
        if evidence_age_days is None:
            blockers.append("Market evidence is missing a valid observation date.")
        elif evidence_age_days > MAX_MARKET_EVIDENCE_AGE_DAYS:
            blockers.append(
                f"Refresh market evidence; the matched demand/supply pair is {evidence_age_days} days old."
            )

    components: dict[str, float | None] = {
        "demand": None,
        "market_balance": None,
        "contribution_margin": None,
        "sample_depth": None,
    }
    score = None
    contribution_profit = None
    contribution_margin_rate = None
    if market_pair and economics:
        demand = float(market_pair["demand"])
        supply = float(market_pair["supply"])
        price = float(economics["sale_price_usd"])
        contribution_profit = float(economics["contribution_profit_usd"])
        contribution_margin_rate = contribution_profit / price if price > 0 else None

        if demand <= 0:
            blockers.append("Measured demand must be greater than zero.")
        if supply <= 0:
            blockers.append("Measured marketplace supply must be greater than zero.")
        if price <= 0:
            blockers.append("Sale price must be greater than zero.")
        if contribution_profit <= 0:
            blockers.append("Contribution profit must be positive before product development advances.")

        if demand > 0 and supply > 0 and contribution_margin_rate is not None:
            components = {
                "demand": _round_score(25 * math.log10(demand + 1)),
                "market_balance": _round_score(
                    50 + 20 * math.log10(demand / supply)
                ),
                "contribution_margin": _round_score(
                    (contribution_margin_rate / 0.60) * 100
                ),
                "sample_depth": _round_score((sample_count / 100) * 100),
            }
            score = round(
                components["demand"] * 0.35
                + components["market_balance"] * 0.25
                + components["contribution_margin"] * 0.30
                + components["sample_depth"] * 0.10,
                1,
            )

    if trend is None:
        cautions.append("No dated trend series is attached; seasonality remains untested.")
    if outcome_count == 0:
        cautions.append("No own-shop outcome exists; this is a pre-launch decision, not a sales prediction.")

    confidence = _confidence_score(
        has_market_pair=market_pair is not None,
        sample_count=sample_count,
        has_economics=economics is not None,
        has_trend=trend is not None,
        has_outcomes=outcome_count > 0,
    )
    status = _decision_status(score, blockers)
    snapshot = {
        "keyword": keyword,
        "product_type": normalized_product,
        "market_pair": market_pair,
        "unit_economics": economics,
        "listing_sample_count": sample_count,
        "trend": trend,
        "outcome_period_count": outcome_count,
        "evidence_age_days": evidence_age_days,
    }
    fingerprint = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()

    return {
        "keyword": keyword,
        "product_type": normalized_product,
        "model_version": MODEL_VERSION,
        "evaluated_at": now.astimezone(timezone.utc).isoformat(),
        "status": status,
        "score": score,
        "confidence": confidence,
        "ready_to_advance": status in {"advance", "review"} and not blockers,
        "components": components,
        "evidence": snapshot,
        "blockers": _dedupe(blockers),
        "cautions": _dedupe(cautions),
        "input_fingerprint": fingerprint,
        "model_notes": [
            "Demand and supply must share a provider and reporting period.",
            "Score weights: demand 35%, market balance 25%, contribution margin 30%, sample depth 10%.",
            "Confidence describes evidence completeness; it is not a probability of success.",
            "The score does not estimate revenue and must be reviewed by an operator before launch.",
        ],
        "economics": {
            "contribution_profit_usd": contribution_profit,
            "contribution_margin_rate": (
                round(contribution_margin_rate, 4)
                if contribution_margin_rate is not None
                else None
            ),
        },
    }


def _latest_market_pair(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = {}
    for row in observations:
        metric = str(row.get("metric") or "").strip().lower()
        if metric not in DEMAND_METRICS and metric not in SUPPLY_METRICS:
            continue
        source = str(row.get("source") or "").strip().lower()
        if not source:
            continue
        period_start = str(row.get("period_start") or "").strip()
        period_end = str(row.get("period_end") or "").strip()
        if not period_start and not period_end:
            observed_day = str(row.get("observed_at") or "").strip()[:10]
            period_start = observed_day
            period_end = observed_day
        key = (
            source,
            str(row.get("geography") or "").strip().upper(),
            period_start,
            period_end,
        )
        kind = "demand" if metric in DEMAND_METRICS else "supply"
        existing = grouped.setdefault(key, {}).get(kind)
        if existing is None or _date_sort_key(row) > _date_sort_key(existing):
            grouped[key][kind] = row

    pairs: list[dict[str, Any]] = []
    for key, values in grouped.items():
        demand_row = values.get("demand")
        supply_row = values.get("supply")
        if not demand_row or not supply_row:
            continue
        demand = _finite_number(demand_row.get("value"))
        supply = _finite_number(supply_row.get("value"))
        if demand is None or supply is None:
            continue
        observed_at = max(
            str(demand_row.get("period_end") or demand_row.get("observed_at") or ""),
            str(supply_row.get("period_end") or supply_row.get("observed_at") or ""),
        )
        pairs.append({
            "source": key[0],
            "geography": key[1] or None,
            "period_start": key[2] or None,
            "period_end": key[3] or None,
            "observed_at": observed_at,
            "demand": demand,
            "demand_metric": str(demand_row.get("metric")),
            "demand_unit": str(demand_row.get("unit") or ""),
            "supply": supply,
            "supply_metric": str(supply_row.get("metric")),
            "supply_unit": str(supply_row.get("unit") or ""),
        })
    return max(pairs, key=lambda row: str(row["observed_at"]), default=None)


def _latest_economics(
    rows: list[dict[str, Any]], product_type: str
) -> dict[str, Any] | None:
    matching = [
        row for row in rows
        if _normalize_product_type(str(row.get("product_type") or "")) == product_type
    ]
    if not matching:
        return None
    row = max(matching, key=_date_sort_key)
    fields = (
        "sale_price_usd",
        "production_cost_usd",
        "shipping_cost_usd",
        "marketplace_fees_usd",
        "advertising_cost_usd",
        "refund_allowance_usd",
        "contribution_profit_usd",
    )
    result = {
        "source": row.get("source"),
        "observed_at": row.get("observed_at"),
        "product_type": product_type,
    }
    for field in fields:
        result[field] = _finite_number(row.get(field))
    return result if all(result[field] is not None for field in fields) else None


def _listing_sample_count(evidence: dict[str, Any]) -> int:
    snapshots = len(evidence.get("listing_snapshots") or [])
    latest = evidence.get("latest_attempt") or {}
    attempted = _finite_number(latest.get("sampled_listing_count")) or 0
    return max(snapshots, int(attempted))


def _trend_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [row for row in rows if _finite_number(row.get("value")) is not None]
    if len(usable) < 2:
        return None
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in usable:
        by_source.setdefault(str(row.get("source") or "unknown"), []).append(row)
    source, points = max(by_source.items(), key=lambda item: len(item[1]))
    points = sorted(points, key=lambda row: str(row.get("point_at") or ""))
    first = float(points[0]["value"])
    last = float(points[-1]["value"])
    change = None if first == 0 else round(((last - first) / abs(first)) * 100, 1)
    return {
        "source": source,
        "point_count": len(points),
        "period_start": points[0].get("point_at"),
        "period_end": points[-1].get("point_at"),
        "first_value": first,
        "last_value": last,
        "change_pct": change,
        "unit": points[-1].get("unit"),
    }


def _confidence_score(
    *,
    has_market_pair: bool,
    sample_count: int,
    has_economics: bool,
    has_trend: bool,
    has_outcomes: bool,
) -> float:
    value = 0.0
    if has_market_pair:
        value += 35
    if has_economics:
        value += 25
    value += min(20, sample_count / MIN_LISTING_SAMPLE * 10)
    if has_trend:
        value += 10
    if has_outcomes:
        value += 10
    return round(min(100, value), 1)


def _decision_status(score: float | None, blockers: list[str]) -> str:
    if blockers or score is None:
        return "blocked"
    if score >= 70:
        return "advance"
    if score >= 50:
        return "review"
    return "hold"


def _round_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _date_sort_key(row: dict[str, Any]) -> str:
    return str(row.get("period_end") or row.get("observed_at") or row.get("point_at") or "")


def _age_days(value: Any, now: datetime) -> int | None:
    observed = _parse_datetime(value)
    if observed is None:
        return None
    return max(0, (now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).days)


def _normalize_product_type(value: str) -> str:
    normalized = "_".join(value.strip().lower().replace("-", " ").split())
    return normalized or "unspecified"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
