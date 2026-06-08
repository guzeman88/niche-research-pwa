"""Research router — run research, list reports, get report details."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from models.schemas import ResearchRunRequest, ResearchRunResponse, ReportListItem
from services.research_service import start_research_background, get_run_status
from config import WORKSPACE

router = APIRouter(prefix="/api/research", tags=["research"])


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
            report_id=f"rpt_{kw.replace(' ','_')[:30]}_{scan_date[:10] if scan_date else 'unknown'}",
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
    if not report_dir.exists():
        raise HTTPException(status_code=404, detail="No reports directory found")

    for f in sorted(report_dir.glob("niche_report_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("report_id") == report_id:
                return data
        except Exception:
            continue

    raise HTTPException(status_code=404, detail=f"Report {report_id} not found")


@router.get("/runs/{run_id}")
def run_status(run_id: str):
    """Get the status of a running/finished research job."""
    status = get_run_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return status
