"""Private evidence operations for auditable market and profitability inputs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from models.schemas import EvidenceImportRequest, KeywordOutcomeRequest, ProductEconomicsRequest

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


def _db():
    from pipeline import keyword_database as kdb
    kdb.init_db()
    return kdb


@router.get("/coverage")
def evidence_coverage(run_limit: int = Query(default=20, ge=1, le=100)):
    return _db().get_evidence_coverage(run_limit=run_limit)


@router.post("/import", status_code=201)
def import_keyword_evidence(req: EvidenceImportRequest):
    from services.evidence_import_service import import_evidence
    try:
        return import_evidence(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.get("/{keyword}")
def keyword_evidence(keyword: str, limit: int = Query(default=100, ge=1, le=500)):
    result = _db().get_keyword_evidence(keyword, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return result
