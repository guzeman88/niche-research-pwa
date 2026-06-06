"""Export router — CSV and JSON export of keyword data."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/export", tags=["export"])


def _ensure_db():
    from pipeline import keyword_database as kdb
    kdb.init_db()


@router.get("/csv")
def export_csv(domain: str | None = None, sort_by: str = "gap_score"):
    """Export top opportunities/gaps as CSV."""
    _ensure_db()
    from pipeline import keyword_database as kdb

    tmp = Path(tempfile.gettempdir()) / f"etsy_niche_export_{sort_by}.csv"
    count = kdb.export_csv(str(tmp), domain=domain, sort_by=sort_by)
    if count == 0:
        return {"exported": 0, "message": "No data to export"}
    return FileResponse(
        path=str(tmp),
        filename=f"niche_research_{sort_by}.csv",
        media_type="text/csv",
    )


@router.get("/json")
def export_json(include_raw: bool = False):
    """Export full database snapshot as JSON."""
    _ensure_db()
    from pipeline import keyword_database as kdb

    tmp = Path(tempfile.gettempdir()) / "etsy_niche_export.json"
    count = kdb.export_json(str(tmp), include_raw_scans=include_raw)
    if count == 0:
        return {"exported": 0, "message": "No data to export"}
    return FileResponse(
        path=str(tmp),
        filename="niche_research_export.json",
        media_type="application/json",
    )
