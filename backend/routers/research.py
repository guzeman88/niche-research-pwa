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
    """List recent niche research reports."""
    from pipeline.stages.niche_research import list_reports as _list_reports
    from pipeline.stages.niche_research import load_latest_report

    reports = []
    paths = _list_reports(store_slug)[:limit]
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            reports.append(ReportListItem(
                report_id=data.get("report_id", p.stem),
                store_slug=data.get("store_slug", store_slug),
                seed_keywords=data.get("seed_keywords", []),
                opportunity_score=data.get("opportunity_score", 0.0),
                demand_score=data.get("demand_score", 0.0),
                competition_score=data.get("competition_score", 0.0),
                margin_score=data.get("margin_score", 0.0),
                trend_velocity_score=data.get("trend_velocity_score", 0.0),
                generated_at=data.get("generated_at", ""),
                sources_used=data.get("sources_used", []),
            ))
        except Exception:
            continue
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
