"""Operator-only reference collection and model comparison; never public snapshots."""
import json
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import Response
from pydantic import ValidationError
from services.sales_intelligence import anchored, consensus, estimator, features, ingestion, registry, service, store, training, worker

router = APIRouter(prefix='/api/sales-intelligence', tags=['private sales intelligence'])


def invoke(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except ValidationError as exc:
        raise HTTPException(400, exc.errors()[0]['msg']) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)[:250]) from exc


def bounded(data):
    if len(json.dumps(data).encode()) > ingestion.MAX_BYTES + 20000:
        raise HTTPException(413, 'Import at most 2 MB per request')


@router.get('')
def overview(q: str = Query('', max_length=200), page: int = Query(0, ge=0, le=50000)):
    return service.overview(q, page)


@router.get('/sources')
def sources():
    return {'items': registry.sources(), 'owner': 'etgen_backend'}


@router.post('/sources/{source_id}/pause')
def source_pause(source_id: str):
    return invoke(registry.pause, source_id, True)


@router.post('/sources/{source_id}/resume')
def source_resume(source_id: str):
    return invoke(registry.pause, source_id, False)


@router.post('/sources/{source_id}/test')
def source_test(source_id: str):
    source = invoke(registry.source, source_id)
    if source['automation'] == 'supported_api_configured' and not source['paused']:
        return invoke(worker.dispatch_collection, source_id)
    return {'id': source_id, 'external_requests': 0, 'status': 'export_ready' if source['capabilities']['storage'] else 'access_unverified',
            'reason': source['reason'], 'capabilities': source['capabilities'], 'verified_automated_api': False}


@router.get('/coverage')
def coverage():
    return service.coverage()


@router.get('/estimates')
def estimates():
    return estimator.overview()


@router.get('/anchored')
def anchored_estimates():
    return anchored.overview()


@router.post('/estimates/refresh', status_code=202)
def refresh_estimates():
    return worker.enqueue('estimate')


@router.post('/listings/{listing_id}/track')
def track(listing_id: str):
    return invoke(estimator.track, listing_id)


@router.get('/opportunities')
def opportunities():
    return service.opportunities()


@router.get('/collection/plan')
def collection_plan():
    return worker.plan()


@router.post('/collection/run', status_code=202)
def collect():
    return invoke(worker.dispatch_collection)


@router.post('/catalog/refresh', status_code=202)
def catalog():
    return worker.enqueue('catalog')


@router.post('/panels')
def panel(data: dict = Body(...)):
    return invoke(features.panel, int(data.get('size', 30)))


@router.get('/panels')
def panels():
    with store.database() as con:
        return {'items': [{'id': r['id'], **json.loads(r['payload'])} for r in con.execute('SELECT * FROM panels ORDER BY rowid DESC LIMIT 20')]}


@router.post('/imports/preview')
def import_preview(data: dict = Body(...)):
    bounded(data)
    return {k: v for k, v in invoke(ingestion.preview, data).items() if k != '_rows'}


@router.post('/imports/commit')
def import_commit(data: dict = Body(...)):
    bounded(data)
    return invoke(ingestion.commit, data)


@router.post('/outcomes/import')
def outcomes(data: dict = Body(...)):
    bounded(data)
    return invoke(ingestion.import_outcomes, data)


@router.get('/listings/{listing_id}/comparison')
def comparison(listing_id: str, as_of: str | None = Query(None, max_length=50)):
    if not listing_id.isdecimal() or len(listing_id) > 30:
        raise HTTPException(400, 'Use a numeric Etsy listing ID')
    return invoke(service.comparison, listing_id, as_of)


@router.post('/listings/{listing_id}/promote', status_code=202)
def promote(listing_id: str, data: dict = Body(...)):
    return invoke(service.queue_promotion, listing_id, data.get('opportunity_id'))


@router.post('/listings/{listing_id}/investigate')
def investigate(listing_id: str):
    return invoke(service.investigate, listing_id)


@router.get('/listings/{listing_id}/export')
def export(listing_id: str):
    if not listing_id.isdecimal():
        raise HTTPException(400, 'Use a numeric listing ID')
    return Response(service.export_csv(listing_id), media_type='text/csv', headers={'Cache-Control': 'private, no-store',
                    'Content-Disposition': f'attachment; filename="listing-{listing_id}-references.csv"'})


@router.get('/jobs')
def jobs():
    with store.database() as con:
        rows = con.execute('SELECT id,source_id,status,due_at,attempts,result FROM jobs ORDER BY due_at DESC LIMIT 50').fetchall()
        return {'items': [{**dict(r), 'result': json.loads(r['result']) if r['result'] else None} for r in rows]}


@router.post('/pause')
def pause(data: dict = Body(...)):
    if not isinstance(data.get('paused'), bool):
        raise HTTPException(400, 'Supply a pause state')
    with store.database(True) as con:
        store.set_control(con, 'paused', data['paused'])
        store.audit(con, 'worker_pause', {'paused': data['paused']})
    return {'paused': data['paused']}


@router.get('/models')
def models():
    return {'items': training.list_models(), 'actual_outcomes': store.counts()['outcomes']}


@router.post('/models/train', status_code=202)
def train(data: dict = Body(...)):
    days, unit, objective = data.get('days', 30), data.get('unit', 'purchases'), data.get('objective', 'consensus')
    if days not in (7, 30) or unit not in ('units', 'purchases') or objective not in ('consensus', 'actual'):
        raise HTTPException(400, 'Choose 7/30 days and units/purchases')
    return worker.enqueue('train', {'days': days, 'unit': unit, 'objective': objective})


@router.post('/models/{model_id}/activate')
def activate(model_id: str):
    return invoke(training.activate, model_id)


@router.post('/models/rollback')
def rollback(data: dict = Body(...)):
    return invoke(training.rollback, data.get('days', 30), data.get('unit', 'purchases'), data.get('lane', 'consensus_student'))


@router.post('/models/{model_id}/evaluate', status_code=202)
def evaluate(model_id: str):
    return worker.enqueue('evaluate_actual', {'model_id': model_id})
