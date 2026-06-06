"""Stats router — database statistics and health."""
from __future__ import annotations

from fastapi import APIRouter
from models.schemas import StatsResponse, HealthResponse

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _ensure_db():
    from pipeline import keyword_database as kdb
    kdb.init_db()


@router.get("", response_model=StatsResponse)
def stats():
    """Get keyword database statistics."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    data = kdb.get_stats()
    return StatsResponse(**data)


@router.get("/health", response_model=HealthResponse)
def health():
    """Get database health information."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    data = kdb.get_health()
    return HealthResponse(**data)
