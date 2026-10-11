"""Operator-only product validation, with explicit local-save and mirror status."""
from fastapi import APIRouter, Body, HTTPException
from services import product_validation as service

router = APIRouter(prefix="/api/product-validation", tags=["product validation"])


def invoke(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def overview():
    return {"projects": [service.summary(row["project_id"]) for row in service.records(kind="project")],
        "model_version": service.MODEL_VERSION, "pending_sync": sum(row["sync_status"] == "pending" for row in service.records())}


@router.post("/projects", status_code=201)
def create(data: dict = Body(...)):
    return invoke(service.create_project, data)


@router.get("/export")
def export():
    return service.export_ledger()


@router.post("/sync")
def sync():
    return service.retry_sync()


@router.post("/projects/{project_id}/outcomes/import")
def import_outcomes(project_id: str, data: dict = Body(...), commit: bool = False):
    return invoke(service.import_outcomes_csv, project_id, data, commit=commit)


@router.post("/projects/{project_id}/collect-etsy")
def collect_etsy(project_id: str, data: dict = Body(...)):
    return invoke(service.collect_etsy, project_id, str(data.get("keyword") or ""))


@router.post("/projects/{project_id}/orders/import")
def import_orders(project_id: str, data: dict = Body(...), commit: bool = False):
    return invoke(service.import_orders_csv, project_id, data, commit=commit)


# Declare named operations before the generic evidence-kind route so collect-etsy
# is dispatched to the provider rather than interpreted as an unknown kind.
@router.post("/projects/{project_id}/{kind}", status_code=201)
def save(project_id: str, kind: str, data: dict = Body(...)):
    actions = {"market": service.save_market, "competitors": service.import_competitor_csv,
        "economics": service.save_economics, "outcome": service.save_outcome,
        "google": service.import_google_package, "review-competitors": service.review_competitors}
    if kind not in actions:
        raise HTTPException(status_code=404, detail="Unknown evidence type")
    result = invoke(actions[kind], project_id, data)
    return {**result, "project": invoke(service.summary, project_id)}
