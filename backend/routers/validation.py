"""Automated keyword-validation report and collector controls."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/validation", tags=["validation"])

_job_lock = threading.Lock()
_job: dict = {"status": "idle", "started_at": None, "completed_at": None, "result": None, "error": None}


@router.get("/report")
def report():
    from services.keyword_validation_pipeline import load_validation_report
    return load_validation_report()


@router.get("/status")
def status():
    from adapters.research.google_ads_keyword_planner import is_google_ads_configured
    return {**_job, "configured": is_google_ads_configured()}


@router.get("/test-result/{candidate_id}")
def test_result(candidate_id: str):
    """Evaluate stored listing outcomes against one candidate's hard test plan."""
    from services.keyword_validation_pipeline import load_validation_report
    report = load_validation_report()
    candidates = (report.get("test_portfolio") or {}).get("stores") or []
    candidate = next((row for row in candidates if row.get("id") == candidate_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Test candidate not found")
    from pipeline import keyword_database as kdb
    kdb.init_db()
    outcomes = []
    for product in candidate.get("product_candidates") or []:
        evidence = kdb.get_keyword_evidence(str(product.get("primary_keyword") or ""), limit=500)
        outcomes.extend((evidence or {}).get("outcomes") or [])
    from services.candidate_portfolio import evaluate_candidate_test
    return evaluate_candidate_test(candidate, outcomes)


@router.post("/run", status_code=202)
def run(force: bool = False, expand: bool = True):
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Validation collection is already running")

    _job.update({
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "result": None,
        "error": None,
    })

    def worker() -> None:
        try:
            from services.keyword_validation_pipeline import KeywordValidationPipeline
            result = KeywordValidationPipeline().run(force=force, expand=expand)
            _job.update({"status": result.get("status", "completed"), "result": result})
        except Exception as exc:
            _job.update({"status": "failed", "error": str(exc)})
        finally:
            _job["completed_at"] = datetime.now(timezone.utc).isoformat()
            _job_lock.release()

    threading.Thread(target=worker, daemon=True, name="manual-keyword-validation").start()
    return {"status": "started", "force": force, "expand": expand}
