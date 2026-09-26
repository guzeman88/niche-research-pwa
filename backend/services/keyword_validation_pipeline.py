"""Bulk, token-free keyword collection and deterministic opportunity screening."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from adapters.research.google_ads_keyword_planner import GoogleAdsKeywordPlannerAdapter
from pipeline import keyword_database as kdb


PIPELINE_VERSION = "etgen-keyword-validation-v1.0.0"
PROVIDER = "google_ads_keyword_planner"
STATE_PATH = Path(__file__).parent.parent / "workspace/_keyword_db/google_ads_pipeline_state.json"
REPORT_PATH = Path(__file__).parent.parent / "workspace/_keyword_db/validation_report.json"
SCORE_WEIGHTS = {
    "demand": 35,
    "competition": 25,
    "trend": 20,
    "buyer_intent": 10,
    "profit": 10,
}

_RUN_LOCK = threading.Lock()


class KeywordValidationPipeline:
    """Generate, measure, persist, and rank keywords without model calls."""

    def __init__(self, log_fn=None) -> None:
        self._log = log_fn or print
        self._adapter = GoogleAdsKeywordPlannerAdapter()

    def run(self, *, force: bool = False, expand: bool = True) -> dict[str, Any]:
        if not _RUN_LOCK.acquire(blocking=False):
            return {"status": "already_running", "version": PIPELINE_VERSION}
        started = datetime.now(timezone.utc)
        try:
            kdb.init_db()
            kdb.load_seeds_from_library()
            if not self._adapter.is_configured():
                result = {
                    "status": "not_configured",
                    "version": PIPELINE_VERSION,
                    "required": [
                        "GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID",
                        "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
                        "GOOGLE_ADS_CUSTOMER_ID",
                    ],
                }
                _record_telemetry(started, result, configured=False)
                return result

            state = _load_state()
            expansion = self._expand_keywords(state, force=force) if expand else _empty_expansion()
            metrics = self._collect_metrics(force=force)
            report = build_validation_report()
            completed = datetime.now(timezone.utc)
            state.update({
                "last_run_at": completed.isoformat(),
                "last_status": "completed",
                "last_metrics": metrics,
            })
            if expansion["ran"]:
                state["last_expansion_at"] = completed.isoformat()
            _save_state(state)
            result = {
                "status": "completed",
                "version": PIPELINE_VERSION,
                "started_at": started.isoformat(),
                "completed_at": completed.isoformat(),
                "duration_seconds": round((completed - started).total_seconds(), 2),
                "expansion": expansion,
                "metrics": metrics,
                "report": {
                    "keywords": len(report["keywords"]),
                    "niches": len(report["niches"]),
                    "finalists": len(report["finalists"]),
                    "path": str(REPORT_PATH),
                },
            }
            _record_telemetry(started, result, configured=True)
            return result
        except Exception as exc:
            result = {
                "status": "failed",
                "version": PIPELINE_VERSION,
                "error": str(exc),
            }
            _record_telemetry(started, result, configured=True)
            raise
        finally:
            _RUN_LOCK.release()

    def _expand_keywords(self, state: dict[str, Any], *, force: bool) -> dict[str, Any]:
        refresh_days = _positive_int("GOOGLE_ADS_IDEA_REFRESH_DAYS", 30, maximum=365)
        last_expansion = _parse_datetime(state.get("last_expansion_at"))
        if not force and last_expansion and datetime.now(timezone.utc) - last_expansion < timedelta(days=refresh_days):
            return {**_empty_expansion(), "reason": "refresh_window"}

        seed_limit = _positive_int("GOOGLE_ADS_SEED_LIMIT", 500, maximum=10_000)
        max_new = _positive_int("GOOGLE_ADS_MAX_NEW_KEYWORDS", 50_000, maximum=250_000)
        per_request = _positive_int("GOOGLE_ADS_IDEAS_PER_REQUEST", 2_000, maximum=10_000)
        seeds = [
            row["keyword"] for row in kdb.get_all_seeds()
            if row.get("source") == "library" and kdb.is_scanworthy_seed(row["keyword"])
        ][:seed_limit]
        if not seeds:
            return {**_empty_expansion(), "reason": "no_seeds"}

        before = {row["keyword"] for row in kdb.get_all_seeds()}
        discovered: dict[str, Any] = {}
        requests = 0
        for seed_batch in _chunks(seeds, self._adapter.MAX_IDEA_SEEDS):
            if len(discovered) >= max_new:
                break
            request_limit = min(per_request, max_new - len(discovered))
            self._log(
                f"[google_ads] Expanding {len(seed_batch)} seeds; "
                f"{len(discovered):,}/{max_new:,} unique ideas collected"
            )
            signals = self._adapter.generate_keyword_ideas(seed_batch, max_results=request_limit)
            requests += 1
            fresh = []
            for signal in signals:
                if not kdb.is_scanworthy_seed(signal.keyword):
                    continue
                normalized = " ".join(signal.keyword.lower().split())
                if normalized and normalized not in discovered:
                    discovered[normalized] = signal
                    fresh.append(signal)
            if fresh:
                kdb.save_provider_signal_batch(
                    PROVIDER,
                    fresh,
                    operation="generate_keyword_ideas",
                )

        new_keywords = sum(1 for keyword in discovered if keyword not in before)
        return {
            "ran": True,
            "seed_keywords": len(seeds),
            "requests": requests,
            "ideas_returned": len(discovered),
            "new_keywords": new_keywords,
            "target_maximum": max_new,
        }

    def _collect_metrics(self, *, force: bool) -> dict[str, Any]:
        stale_days = _positive_int("GOOGLE_ADS_METRIC_REFRESH_DAYS", 30, maximum=365)
        cycle_limit = _positive_int("GOOGLE_ADS_KEYWORD_CYCLE_LIMIT", 50_000, maximum=250_000)
        batch_size = _positive_int(
            "GOOGLE_ADS_HISTORICAL_BATCH_SIZE",
            10_000,
            maximum=self._adapter.MAX_HISTORICAL_KEYWORDS,
        )
        if force:
            due = [
                row["keyword"] for row in kdb.get_all_seeds()
                if kdb.is_scanworthy_seed(row["keyword"])
            ][:cycle_limit]
        else:
            due = kdb.get_provider_due_keywords(PROVIDER, stale_days=stale_days, limit=cycle_limit)
        requests = returned = observations = trend_points = 0
        for batch in _chunks(due, batch_size):
            self._log(f"[google_ads] Measuring {len(batch):,} keywords")
            signals = self._adapter.bulk_search(batch)
            persisted = kdb.save_provider_signal_batch(
                PROVIDER,
                signals,
                requested_keywords=batch,
                operation="historical_metrics",
            )
            requests += 1
            returned += persisted["returned_keywords"]
            observations += persisted["observations"]
            trend_points += persisted["trend_points"]
        return {
            "eligible_keywords": len(due),
            "requests": requests,
            "returned_keywords": returned,
            "observations": observations,
            "trend_points": trend_points,
            "batch_size": batch_size,
            "cycle_limit": cycle_limit,
            "refresh_days": stale_days,
        }


def build_validation_report(
    *,
    keyword_limit: int = 200,
    niche_limit: int = 25,
    finalist_limit: int = 5,
    candidate_limit: int = 2_000,
) -> dict[str, Any]:
    """Build a deterministic shortlist from current exact evidence."""
    candidate_keywords = kdb.get_keywords_by_observation(
        PROVIDER,
        "monthly_searches",
        limit=max(keyword_limit, candidate_limit),
    )
    candidates = []
    for keyword in candidate_keywords:
        evidence = kdb.get_keyword_evidence(keyword, limit=500)
        if evidence:
            candidates.append(_score_keyword(evidence))
    candidates.sort(
        key=lambda row: (
            row["screening_score"] is not None,
            row["screening_score"] or -1,
            row["monthly_searches"] or -1,
        ),
        reverse=True,
    )
    shortlisted = candidates[:max(1, min(keyword_limit, 2_000))]
    niches = _build_niches(shortlisted)[:max(1, min(niche_limit, 100))]
    finalists = [niche for niche in niches if niche["keyword_count"] >= 2][
        :max(1, min(finalist_limit, 25))
    ]
    report = {
        "version": PIPELINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weights": SCORE_WEIGHTS,
        "limits": {
            "keyword_shortlist": keyword_limit,
            "niche_shortlist": niche_limit,
            "finalists": finalist_limit,
            "candidate_pool": candidate_limit,
        },
        "keywords": shortlisted,
        "niches": niches,
        "finalists": finalists,
        "notes": [
            "Google Ads supplies search demand and commercial-intent signals.",
            "Etsy Open API supplies marketplace listing supply and listing samples.",
            "Scores remain provisional until every weighted component is observed.",
            "A validation score is a screening aid, not a probability of sales.",
        ],
    }
    _write_json_atomic(REPORT_PATH, report)
    return report


def load_validation_report() -> dict[str, Any]:
    if not REPORT_PATH.exists():
        return build_validation_report()
    try:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else build_validation_report()
    except (OSError, ValueError):
        return build_validation_report()


def _score_keyword(evidence: dict[str, Any]) -> dict[str, Any]:
    observations = evidence.get("observations") or []
    demand_row = _latest_observation(observations, PROVIDER, "monthly_searches")
    supply_row = _latest_observation(observations, "etsy_open_api", "listing_count")
    if supply_row is None:
        supply_row = _latest_observation(observations, "etsy_search_scraper", "listing_count")
    competition_row = _latest_observation(observations, PROVIDER, "google_ads_competition_index")
    cpc_row = _latest_observation(observations, PROVIDER, "average_cpc")
    monthly_searches = _number(demand_row.get("value")) if demand_row else None
    listing_count = _number(supply_row.get("value")) if supply_row else None
    components: dict[str, float | None] = {
        "demand": _clamp(25 * math.log10(monthly_searches + 1)) if monthly_searches is not None else None,
        "competition": (
            _clamp(50 + 20 * math.log10((monthly_searches + 1) / (listing_count + 1)))
            if monthly_searches is not None and listing_count is not None else None
        ),
        "trend": _trend_component(evidence.get("trend_points") or []),
        "buyer_intent": _intent_component(competition_row, cpc_row),
        "profit": _profit_component(evidence.get("product_economics") or []),
    }
    available_weight = sum(
        SCORE_WEIGHTS[name] for name, value in components.items() if value is not None
    )
    weighted_points = sum(
        float(value) * SCORE_WEIGHTS[name] / 100
        for name, value in components.items() if value is not None
    )
    screening_score = round(weighted_points * 100 / available_weight, 1) if available_weight else None
    complete_score = round(weighted_points, 1) if available_weight == 100 else None
    sample_count = len(evidence.get("listing_snapshots") or [])
    blockers = []
    for name, value in components.items():
        if value is None:
            blockers.append(f"Missing {name.replace('_', ' ')} evidence")
    if sample_count < 10:
        blockers.append(f"Only {sample_count} Etsy listing samples; 10 required")
    if complete_score is not None and sample_count >= 10:
        status = "validated" if complete_score >= 70 else "review" if complete_score >= 50 else "hold"
    elif available_weight >= 80 and screening_score is not None and screening_score >= 60:
        status = "promising_incomplete"
    else:
        status = "incomplete"
    seed = evidence.get("seed") or {}
    return {
        "keyword": evidence.get("keyword"),
        "domain": seed.get("domain") or "discovered",
        "status": status,
        "score": complete_score,
        "screening_score": screening_score,
        "evidence_coverage_pct": available_weight,
        "components": components,
        "monthly_searches": monthly_searches,
        "etsy_listing_count": listing_count,
        "listing_samples": sample_count,
        "blockers": blockers,
        "sources": sorted({str(row.get("source")) for row in observations if row.get("source")}),
    }


def _build_niches(keywords: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in keywords:
        grouped[_cluster_key(str(row["keyword"]))].append(row)
    niches = []
    for key, rows in grouped.items():
        ranked = sorted(rows, key=lambda row: row["screening_score"] or -1, reverse=True)
        top = ranked[:10]
        scores = [float(row["screening_score"]) for row in top if row["screening_score"] is not None]
        if not scores:
            continue
        niches.append({
            "id": key.replace(" ", "-"),
            "theme": key.title(),
            "screening_score": round(sum(scores[:3]) / len(scores[:3]), 1),
            "keyword_count": len(rows),
            "validated_keywords": sum(1 for row in rows if row["status"] == "validated"),
            "evidence_coverage_pct": round(
                sum(float(row["evidence_coverage_pct"]) for row in top) / len(top), 1
            ),
            "keywords": top,
        })
    niches.sort(
        key=lambda niche: (
            niche["validated_keywords"], niche["screening_score"], niche["keyword_count"]
        ),
        reverse=True,
    )
    return niches


def _cluster_key(keyword: str) -> str:
    stop = {
        "a", "an", "and", "for", "of", "the", "to", "with", "gift", "gifts",
        "custom", "personalized", "print", "shirt", "mug", "digital", "download",
        "wall", "art", "decor", "svg", "tumbler", "sticker", "tee",
    }
    tokens = [token for token in keyword.lower().replace("-", " ").split() if token not in stop]
    return " ".join(tokens[:2]) or "general"


def _latest_observation(
    rows: list[dict[str, Any]], source: str, metric: str
) -> dict[str, Any] | None:
    matches = [
        row for row in rows
        if row.get("source") == source and row.get("metric") == metric
    ]
    return max(matches, key=lambda row: str(row.get("period_end") or row.get("observed_at") or ""), default=None)


def _trend_component(rows: list[dict[str, Any]]) -> float | None:
    points = [
        row for row in rows
        if row.get("source") == PROVIDER and row.get("unit") == "searches" and _number(row.get("value")) is not None
    ]
    if len(points) < 2:
        return None
    points.sort(key=lambda row: str(row.get("point_at") or ""))
    first = float(points[0]["value"])
    last = float(points[-1]["value"])
    if first <= 0:
        return 100.0 if last > 0 else 50.0
    change_pct = (last - first) / first * 100
    return _clamp(50 + change_pct)


def _intent_component(
    competition_row: dict[str, Any] | None,
    cpc_row: dict[str, Any] | None,
) -> float | None:
    competition = _number(competition_row.get("value")) if competition_row else None
    cpc = _number(cpc_row.get("value")) if cpc_row else None
    if competition is None and cpc is None:
        return None
    values = []
    weights = []
    if competition is not None:
        values.append(_clamp(competition))
        weights.append(0.6)
    if cpc is not None:
        values.append(_clamp(cpc / 5.0 * 100))
        weights.append(0.4)
    return round(sum(value * weight for value, weight in zip(values, weights)) / sum(weights), 1)


def _profit_component(rows: list[dict[str, Any]]) -> float | None:
    usable = []
    for row in rows:
        price = _number(row.get("sale_price_usd"))
        profit = _number(row.get("contribution_profit_usd"))
        if price and price > 0 and profit is not None:
            usable.append(_clamp((profit / price) / 0.60 * 100))
    return round(max(usable), 1) if usable else None


def _record_telemetry(started: datetime, result: dict[str, Any], *, configured: bool) -> None:
    try:
        from services.provider_telemetry import record_provider_attempt
        metrics = result.get("metrics") or {}
        expansion = result.get("expansion") or {}
        record_provider_attempt(
            provider=PROVIDER,
            operation="automated_validation_cycle",
            status=str(result.get("status") or "failed"),
            started_at=started,
            keyword_count=int(metrics.get("eligible_keywords") or 0),
            row_count=int(metrics.get("observations") or 0) + int(metrics.get("trend_points") or 0),
            configured=configured,
            error=result.get("error"),
            rate_limit={"requests_per_second": 1, "keywords_per_historical_request": 10_000},
            metadata={
                "pipeline_version": PIPELINE_VERSION,
                "metric_requests": metrics.get("requests", 0),
                "idea_requests": expansion.get("requests", 0),
                "new_keywords": expansion.get("new_keywords", 0),
            },
        )
    except Exception:
        pass


def _chunks(values: list[Any], size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _positive_int(name: str, default: int, *, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0 or value > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    _write_json_atomic(STATE_PATH, state)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _empty_expansion() -> dict[str, Any]:
    return {
        "ran": False,
        "seed_keywords": 0,
        "requests": 0,
        "ideas_returned": 0,
        "new_keywords": 0,
        "target_maximum": _positive_int("GOOGLE_ADS_MAX_NEW_KEYWORDS", 50_000, maximum=250_000),
    }


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 1)
