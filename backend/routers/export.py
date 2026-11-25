"""Export router — CSV and JSON export of keyword data."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get('/public-snapshot')
def public_snapshot():
    from services.public_exports import current_package
    try:return current_package()[1]
    except (OSError,ValueError,KeyError):raise HTTPException(503,'No complete public research package is ready.') from None


@router.get('/public-snapshot/{identity}/{name:path}')
def public_snapshot_file(identity:str,name:str):
    from services.public_exports import package_file
    try:path=package_file(identity,name)
    except (OSError,ValueError,KeyError):raise HTTPException(404,'Public research package file is unavailable.') from None
    return FileResponse(path,media_type='application/json',headers={'Cache-Control':'private, no-store'})


@router.post('/public-snapshot/refresh',status_code=202)
def refresh_public_snapshot(request:Request):
    worker=getattr(request.app.state,'public_export_worker',None)
    if not worker:raise HTTPException(503,'Public research exports are not enabled.')
    return worker.request()


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
