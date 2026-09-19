"""Private evidence operations for auditable market and profitability inputs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from models.schemas import KeywordOutcomeRequest, ProductEconomicsRequest

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


def _db():
    from pipeline import keyword_database as kdb
    kdb.init_db()
    return kdb


@router.get("/{keyword}")
def keyword_evidence(keyword: str, limit: int = Query(default=100, ge=1, le=500)):
    result = _db().get_keyword_evidence(keyword, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return result


@router.post("/economics", status_code=201)
def add_product_economics(req: ProductEconomicsRequest):
    try:
        contribution = _db().record_product_economics(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "recorded", "contribution_profit_usd": contribution}


@router.post("/outcomes", status_code=201)
def add_keyword_outcome(req: KeywordOutcomeRequest):
    try:
        contribution = _db().record_keyword_outcome(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "recorded", "contribution_profit_usd": contribution}
