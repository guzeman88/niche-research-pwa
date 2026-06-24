"""Research router — run research, list reports, get report details."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from models.schemas import ResearchRunRequest, ResearchRunResponse, ReportListItem
from services.research_service import start_research_background, get_run_status
from config import WORKSPACE

router = APIRouter(prefix="/api/research", tags=["research"])


def _report_id_for_row(row: dict) -> str:
    scan_date = row.get("scanned_at", "")
    keyword = row.get("keyword", "")
    return f"rpt_{keyword.replace(' ','_')[:30]}_{scan_date[:10] if scan_date else 'unknown'}"


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _price_sweet_spot(avg_price: float) -> str:
    if avg_price <= 0:
        return ""
    low = max(1.0, avg_price * 0.8)
    high = avg_price * 1.2
    return f"${low:.0f}-${high:.0f}"


def _db_report_from_opportunity(row: dict, store_slug: str) -> dict:
    keyword = row.get("keyword", "")
    avg_price = _as_float(row.get("avg_price_usd"))
    monthly_revenue = _as_float(row.get("monthly_revenue_usd"))
    competition_quality = _as_float(row.get("competition_quality"))
    listing_count = _as_int(row.get("listing_count"))
    price_sweet_spot = _price_sweet_spot(avg_price)
    report_id = _report_id_for_row(row)

    return {
        "store_slug": store_slug,
        "generated_at": row.get("scanned_at") or "",
        "seed_keywords": [keyword] if keyword else [],
        "keyword_signals": [{
            "keyword": keyword,
            "monthly_searches": 0,
            "competition_score": _as_float(row.get("competition_score")),
            "avg_price_usd": avg_price,
            "trend_direction": row.get("trajectory") or "stable",
            "source": "keyword_database",
        }],
        "keyword_search_data": [{
            "keyword": keyword,
            "total_listing_count": listing_count,
            "avg_price_usd": avg_price,
            "price_min": 0,
            "price_p25": 0,
            "price_median": avg_price,
            "price_p75": 0,
            "price_max": 0,
            "price_sweet_spot": price_sweet_spot,
            "avg_review_count": 0,
            "pct_star_sellers": 0,
            "pct_bestsellers": 0,
            "competition_quality_score": competition_quality,
            "estimated_market_monthly_revenue_usd": monthly_revenue,
            "top_listing_titles": [],
            "avg_favorites": 0,
            "max_favorites": 0,
            "pct_high_favorites": 0,
        }],
        "demand_score": _as_float(row.get("demand_score")),
        "competition_score": _as_float(row.get("competition_score")),
        "margin_score": _as_float(row.get("margin_score")),
        "trend_velocity_score": _as_float(row.get("trend_score")),
        "opportunity_score": _as_float(row.get("opportunity_score")),
        "avg_price_usd": avg_price,
        "price_sweet_spot": price_sweet_spot,
        "estimated_market_monthly_revenue_usd": monthly_revenue,
        "avg_competition_quality": competition_quality,
        "seasonality": [],
        "peak_months": _json_list(row.get("peak_months")),
        "keyword_clusters": [],
        "underserved_angles": [],
        "winning_styles": [],
        "recommended_product_types": [],
        "competitor_gaps": [],
        "pricing_insights": "",
        "entry_strategy": row.get("entry_strategy") or "",
        "sources_used": ["keyword_database"],
        "report_id": report_id,
    }


@router.post("/run", response_model=ResearchRunResponse)
def run_research(req: ResearchRunRequest):
    """Start a niche research run in the background. Returns run_id for SSE tracking."""
    run_id = start_research_background(
        keywords=req.keywords,
        store_slug=req.store_slug,
        skip_scraper=req.skip_scraper,
        adapter_names=req.adapter_names,
    )
    return ResearchRunResponse(run_id=run_id, status="started",
                               message=f"Research started for: {req.keywords}")


@router.get("/reports", response_model=list[ReportListItem])
def list_reports(store_slug: str = "__global__", limit: int = 50):
    """List recent niche research reports — pulled from keyword database for accurate scores."""
    from pipeline import keyword_database as kdb
    kdb.init_db()

    # Get top opportunities as report-like items
    opps = kdb.get_top_opportunities(limit=limit)
    reports = []
    for o in opps:
        scan_date = o.get("scanned_at", "")
        kw = o.get("keyword", "")
        reports.append(ReportListItem(
            report_id=_report_id_for_row(o),
            store_slug=store_slug,
            seed_keywords=[kw],
            opportunity_score=o.get("opportunity_score", 0) or 0,
            demand_score=o.get("demand_score", 0) or 0,
            competition_score=o.get("competition_score", 0) or 0,
            margin_score=o.get("margin_score", 0) or 0,
            trend_velocity_score=o.get("trend_score", 0) or 0,
            generated_at=scan_date,
            sources_used=[],
        ))
    return reports


@router.get("/reports/latest")
def latest_report(store_slug: str = "__global__"):
    """Get the most recent niche research report."""
    from pipeline.stages.niche_research import load_latest_report
    report = load_latest_report(store_slug)
    if report is None:
        raise HTTPException(status_code=404, detail="No reports found")
    from dataclasses import asdict
    return asdict(report)


@router.get("/reports/{report_id}")
def get_report(report_id: str, store_slug: str = "__global__"):
    """Get a specific report by ID."""
    report_dir = WORKSPACE / store_slug / "_niche_research"
    if report_dir.exists():
        for f in sorted(report_dir.glob("niche_report_*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("report_id") == report_id:
                    return data
            except Exception:
                continue

    from pipeline import keyword_database as kdb
    kdb.init_db()
    for row in kdb.get_top_opportunities(limit=10000):
        if _report_id_for_row(row) == report_id:
            return _db_report_from_opportunity(row, store_slug)

    raise HTTPException(status_code=404, detail=f"Report {report_id} not found")


@router.get("/runs/{run_id}")
def run_status(run_id: str):
    """Get the status of a running/finished research job."""
    status = get_run_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return status
