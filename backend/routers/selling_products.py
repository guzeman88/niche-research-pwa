"""Operator-only selling-products research, imports and original briefs."""
import json
from fastapi import APIRouter, Body, HTTPException, Query, Response
from pydantic import ValidationError
from services import selling_products as service

router = APIRouter(prefix='/api/selling-products', tags=['selling products'])


def invoke(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except service.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(400, exc.errors()[0]['msg']) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('')
def overview(q: str = Query('', max_length=200), stage: str = Query('', max_length=20)):
    return service.overview(q, stage)


@router.get('/research')
def research(keyword: str = Query(..., min_length=3, max_length=160)):
    return invoke(service.research, keyword)


@router.post('/opportunities', status_code=201)
def create(data: dict = Body(...)):
    return invoke(service.save_opportunity, data)


@router.get('/opportunities/{opportunity_id}')
def detail(opportunity_id: str):
    return invoke(service.detail, opportunity_id)


@router.post('/opportunities/{opportunity_id}')
def update(opportunity_id: str, data: dict = Body(...)):
    return invoke(service.save_opportunity, data.get('opportunity'), opportunity_id, data.get('expected_fingerprint'))


@router.post('/opportunities/{opportunity_id}/preview')
def preview(opportunity_id: str, data: dict = Body(...)):
    return invoke(service.preview, opportunity_id, data)


@router.post('/opportunities/{opportunity_id}/import')
def import_packet(opportunity_id: str, data: dict = Body(...)):
    if len(json.dumps(data).encode()) > service.MAX_BYTES:
        raise HTTPException(400, 'Import at most 2 MB at a time')
    return invoke(service.import_packet, opportunity_id, data)


@router.post('/opportunities/{opportunity_id}/brief')
def brief(opportunity_id: str, data: dict = Body(...)):
    return invoke(service.save_brief, opportunity_id, data)


@router.get('/opportunities/{opportunity_id}/export')
def export(opportunity_id: str, response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    return invoke(service.export, opportunity_id)


@router.get('/opportunities/{opportunity_id}/production-intake')
def production(opportunity_id: str):
    return invoke(service.production_intake, opportunity_id)


@router.post('/opportunities/{opportunity_id}/validation')
def validation(opportunity_id: str):
    return invoke(service.link_validation, opportunity_id)
