"""Gaps router — gap analysis reports and top gaps."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/gaps", tags=["gaps"])


def _ensure_db():
    from pipeline import keyword_database as kdb
    kdb.init_db()


@router.get("")
def top_gaps(limit: int = Query(default=100, le=500), min_score: float = 0.0):
    """Get top gap reports ranked by composite gap score."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    return kdb.get_top_gap_reports(limit=limit, min_score=min_score)


@router.get("/{keyword}")
def get_gap_report(keyword: str):
    """Get the most recent gap report for a specific keyword."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    report = kdb.get_gap_report(keyword)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No gap report for '{keyword}'")
    return report
