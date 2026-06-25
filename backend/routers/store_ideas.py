"""Profit-ranked generated store ideas."""
from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/store-ideas", tags=["store-ideas"])


def _ensure_db():
    from pipeline import keyword_database as kdb
    kdb.ensure_seed_snapshot()
    kdb.init_db()
    kdb.load_seeds_from_library()


@router.get("/profitable")
def profitable_store_ideas(
    limit: int = Query(default=12, ge=1, le=48),
    signal_limit: int = Query(default=800, ge=100, le=2000),
    domain: str | None = None,
):
    """Return cached store concepts ranked by profit potential."""
    _ensure_db()
    from pipeline.store_idea_profitability import generate_profitable_store_ideas

    return generate_profitable_store_ideas(limit=limit, signal_limit=signal_limit, domain=domain)
