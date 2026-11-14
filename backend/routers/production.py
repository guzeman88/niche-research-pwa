"""Private operator APIs; no automatic publication or billable provider fallback."""
import base64
import httpx
from fastapi import APIRouter,Body,Depends,HTTPException,Request
from fastapi.responses import FileResponse
from services import production as service

def require_engine():
    if service.Engine is None:
        raise HTTPException(503,'Production engine is not installed. Run the verified backend engine installer; existing research remains available.')


router=APIRouter(prefix='/api/production',tags=['production'],dependencies=[Depends(require_engine)])


def invoke(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    except httpx.HTTPError as exc:raise HTTPException(502,'Provider request failed. Saved receipts preserve progress; reconcile uncertain creation before retrying.') from exc


def mutate(job_id,fn,*args):
    result=invoke(fn,*args)
    service.mirror(service.engine().job(job_id))
    return result


def customer_invoke(method,*args):
    return invoke(lambda: getattr(service.customer_store(),method)(*args))


@router.get('')
def overview():return service.overview()


@router.get('/capabilities')
def capabilities():return invoke(service.renderer_capabilities)


@router.get('/launch-recipes')
def launch_recipes():return invoke(service.launch_recipes)


@router.post('/cost-plan/preview')
def preview_cost(data:dict=Body(...)):
    from etgen_production.costs import estimate_plan
    return invoke(estimate_plan,data.get('price'),data.get('cost_plan'))


@router.get('/etsy/status')
def seller_status(request:Request):
    from services.seller_connection import configured_store,account_id,ConnectionFailure
    try:return configured_store().status(account_id(request))
    except ConnectionFailure as exc:return {'configured':False,'connected':False,'reason':str(exc),'automatic_publication':False}


@router.post('/etsy/connect/start')
def seller_start(request:Request):
    from services.seller_connection import configured_store,account_id
    return invoke(lambda:configured_store().start(account_id(request)))


@router.post('/etsy/connect/complete')
def seller_complete(request:Request,data:dict=Body(...)):
    from services.seller_connection import configured_store,account_id
    return invoke(lambda:configured_store().complete(account_id(request),data.get('state'),data.get('code')))


@router.get('/etsy/orders')
def seller_orders(request:Request):
    from services.seller_connection import configured_store,account_id
    from services.seller_orders import OrderCapture
    return invoke(lambda:OrderCapture(configured_store()).summary(account_id(request)))


@router.post('/etsy/orders/sync')
def sync_seller_orders(request:Request):
    from services.seller_connection import configured_store,account_id
    from services.seller_orders import OrderCapture
    return invoke(lambda:OrderCapture(configured_store()).sync(account_id(request)))


@router.post('/etsy/orders/support')
def save_support(request:Request,data:dict=Body(...)):
    from services.seller_connection import configured_store,account_id
    from services.seller_orders import OrderCapture
    return invoke(lambda:OrderCapture(configured_store()).support(account_id(request),data.get('order_key'),data.get('minutes')))


@router.post('/jobs/{job_id}/listing-images')
def listing_images(job_id:str,data:dict=Body(...)):
    values=data.get('images')
    if not isinstance(values,list) or not 1<=len(values)<=10 or any(not isinstance(value,str) or len(value)>12*1024*1024 for value in values):
        raise HTTPException(400,'Supply one to ten bounded PNG images')
    try:images=[base64.b64decode(value,validate=True) for value in values]
    except (ValueError,TypeError):raise HTTPException(400,'Listing images need valid base64 PNG contents') from None
    return mutate(job_id,service.engine().attach_listing_images,job_id,images,data.get('source_artifact_fingerprint'))


def seller_credentials(request):
    from services.seller_connection import configured_store,account_id,ConnectionFailure
    from etgen_production.marketplace import configured
    try:store=configured_store()
    except ConnectionFailure:
        if configured()['etsy']:return None # Preserve separately reviewed legacy operator configuration.
        raise
    return store.credentials(account_id(request))


@router.post('/jobs',status_code=201)
def submit(data:dict=Body(...)):return invoke(service.submit,data)


@router.post('/pattern-fingerprint')
def pattern_fingerprint(data:dict=Body(...)):
    try:
        from etgen_production.builders import pattern_source_fingerprint
    except ImportError as exc:
        raise HTTPException(503,'Install the verified pattern publishing engine first') from exc
    payload=data.get('product_data')
    import json
    if not isinstance(payload,dict) or len(json.dumps(payload))>100000:
        raise HTTPException(400,'Supply bounded authored pattern content')
    return {'fingerprint':invoke(pattern_source_fingerprint,payload),'maker_test_verified':False}


@router.get('/jobs/{job_id}')
def job(job_id:str):return invoke(service.engine().job,job_id)


@router.post('/jobs/{job_id}/review')
def review(job_id:str,data:dict=Body(...)):
    return mutate(job_id,service.engine().review,job_id,data)


@router.post('/jobs/{job_id}/export')
def export(job_id:str):return mutate(job_id,service.engine().export,job_id)


@router.post('/jobs/{job_id}/action')
def action(job_id:str,data:dict=Body(...)):return mutate(job_id,service.engine().action,job_id,data.get('action'))


@router.get('/jobs/{job_id}/files/{name:path}')
def file(job_id:str,name:str):
    path=invoke(service.engine().file,job_id,name)
    return FileResponse(path,filename=name,headers={'Cache-Control':'private, no-store'})


@router.get('/customers')
def customers():return customer_invoke('list_instances')


@router.post('/customers',status_code=201)
def customer_create(data:dict=Body(...)):return customer_invoke('create',data)


@router.get('/customers/{instance_id}')
def customer(instance_id:str):return customer_invoke('get',instance_id)


@router.post('/customers/{instance_id}/photos')
def customer_photo(instance_id:str,data:dict=Body(...)):
    try:
        raw=data.get('base64','')
        if not isinstance(raw,str) or len(raw)>28_000_000:raise ValueError('Photo is too large')
        value=base64.b64decode(raw,validate=True)
    except (ValueError,TypeError) as exc:raise HTTPException(400,'Select a valid photo of at most twenty MB') from exc
    return customer_invoke('import_photo',instance_id,value,data.get('license_note',''),data.get('kind','reference'))


@router.post('/customers/{instance_id}/revise')
def customer_revise(instance_id:str,data:dict=Body(...)):return customer_invoke('revise',instance_id,data)


@router.post('/customers/{instance_id}/produce')
def customer_produce(instance_id:str):return customer_invoke('produce',instance_id)


@router.post('/customers/{instance_id}/cancel')
def customer_cancel(instance_id:str):return customer_invoke('cancel',instance_id)


@router.post('/customers/{instance_id}/review')
def customer_review(instance_id:str,data:dict=Body(...)):return customer_invoke('review_proof',instance_id,data)


@router.post('/customers/{instance_id}/export')
def customer_export(instance_id:str):return customer_invoke('export',instance_id)


@router.get('/customers/{instance_id}/files/{name:path}')
def customer_file(instance_id:str,name:str):
    path=customer_invoke('file',instance_id,name)
    return FileResponse(path,filename=path.name,headers={'Cache-Control':'private, no-store'})


@router.post('/jobs/{job_id}/assess')
def assess(job_id:str,data:dict=Body(...)):return mutate(job_id,service.engine().machine_review,job_id,data.get('vision') is True)


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
    return mutate(job_id,printify_mockups,service.engine(),job_id)


@router.post('/jobs/{job_id}/etsy-draft')
def etsy(job_id:str,request:Request):
    from etgen_production.marketplace import etsy_draft
    # Keep the exact-product gate ahead of credential refresh/provider access.
    engine=service.engine();job=engine.job(job_id)
    if job['status'] not in ('approved','exported'):raise HTTPException(400,'Approve the exact listing and customer files first')
    connection=invoke(seller_credentials,request)
    result=invoke(etsy_draft,engine,job_id,connection=connection)
    if connection is not None:
        from services.seller_connection import configured_store,account_id
        from contextlib import closing
        store=configured_store()
        with closing(store.connect()) as c,c:c.execute('INSERT INTO connection_events(account,event,at) VALUES(?,?,?)',
            (account_id(request),'draft_upload_verified',store.clock()))
    return result


@router.post('/jobs/{job_id}/reconcile-etsy')
def reconcile_etsy(job_id:str,request:Request,data:dict=Body(...)):
    from etgen_production.marketplace import adopt_etsy_draft
    engine=service.engine()
    if engine.job(job_id)['status'] not in ('approved','exported'):raise HTTPException(400,'Approve the exact package before reconciling its draft')
    return invoke(lambda:adopt_etsy_draft(engine,job_id,data.get('listing_id',''),connection=seller_credentials(request)))


@router.post('/jobs/{job_id}/reconcile-printify')
def reconcile_printify(job_id:str,data:dict=Body(...)):
    from etgen_production.marketplace import adopt_printify_product
    return invoke(adopt_printify_product,service.engine(),job_id,data.get('product_id',''))
