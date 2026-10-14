"""Private operator APIs; no automatic publication or billable provider fallback."""
import base64
import httpx
from fastapi import APIRouter,Body,HTTPException
from fastapi.responses import FileResponse
from services import production as service

router=APIRouter(prefix='/api/production',tags=['production'])


def invoke(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    except httpx.HTTPError as exc:raise HTTPException(502,'Provider request failed. Saved receipts preserve progress; reconcile uncertain creation before retrying.') from exc


@router.get('')
def overview():return service.overview()


@router.post('/jobs',status_code=201)
def submit(data:dict=Body(...)):return invoke(service.submit,data)


@router.get('/jobs/{job_id}')
def job(job_id:str):return invoke(service.engine().job,job_id)


@router.post('/jobs/{job_id}/review')
def review(job_id:str,data:dict=Body(...)):
    job=invoke(service.engine().review,job_id,data);service.mirror(job);return job


@router.post('/jobs/{job_id}/export')
def export(job_id:str):return invoke(service.engine().export,job_id)


@router.post('/jobs/{job_id}/action')
def action(job_id:str,data:dict=Body(...)):return invoke(service.engine().action,job_id,data.get('action'))


@router.get('/jobs/{job_id}/files/{name}')
def file(job_id:str,name:str):
    path=invoke(service.engine().file,job_id,name)
    return FileResponse(path,filename=name,headers={'Cache-Control':'private, no-store'})


@router.post('/jobs/{job_id}/assess')
def assess(job_id:str,data:dict=Body(...)):return invoke(service.engine().machine_review,job_id,data.get('vision') is True)


@router.get('/jobs/{job_id}/duplicates')
def duplicates(job_id:str):return invoke(service.engine().duplicates,job_id)


@router.post('/pause')
def pause(data:dict=Body(...)):
    if not isinstance(data.get('paused'),bool):raise HTTPException(400,'Supply an explicit pause value')
    service.engine().pause(data['paused']);return {'paused':data['paused']}


@router.post('/models')
def models(data:dict=Body(...)):return invoke(service.save_models,data)


@router.post('/match')
def match(data:dict=Body(...)):return invoke(service.match,data)


@router.post('/assets',status_code=201)
def asset(data:dict=Body(...)):
    try:
        raw=data.get('base64','')
        if len(raw)>28_000_000:raise ValueError('Artwork is too large')
        value=base64.b64decode(raw,validate=True)
        return service.engine().import_asset(value,data.get('license_note',''))
    except (ValueError,TypeError) as exc:raise HTTPException(400,str(exc)) from exc


@router.post('/products/{product_id}/feedback')
def feedback(product_id:str,data:dict=Body(...)):return invoke(service.engine().feedback,product_id,data)


@router.post('/benchmarks')
def benchmark(data:dict=Body(...)):return invoke(service.engine().benchmark,data)


@router.post('/profiles')
def profile(data:dict=Body(...)):return invoke(service.engine().save_profile,data)


@router.post('/profiles/{profile_id}')
def enable_profile(profile_id:str,data:dict=Body(...)):return invoke(service.engine().enable_profile,profile_id,data.get('enabled'))


@router.get('/training-dataset')
def training():return service.engine().training_dataset()


@router.post('/training')
def training_experiment(data:dict=Body(...)):
    from etgen_production.training import start
    return invoke(start,service.engine(),data.get('profile',''),data.get('approved'))


@router.post('/jobs/{job_id}/mockups')
def mockups(job_id:str):
    from etgen_production.marketplace import printify_mockups
    return invoke(printify_mockups,service.engine(),job_id)


@router.post('/jobs/{job_id}/etsy-draft')
def etsy(job_id:str):
    from etgen_production.marketplace import etsy_draft
    return invoke(etsy_draft,service.engine(),job_id)
