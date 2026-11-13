"""Private app-owned production; research writers and existing ledgers stay separate."""
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import time
try:
    from etgen_production.engine import Engine
    from etgen_production.providers import capabilities,LocalModels,related
except ModuleNotFoundError as exc:
    if exc.name!='etgen_production':raise
    # Older external build settings may omit the optional engine install step.
    # Keep their research API available; private production routes report 503.
    Engine=None
from services import product_validation as validation


def engine():
    if Engine is None:raise ValueError('Install the verified bundled production engine before enabling production')
    return Engine(Path(os.getenv('PRODUCTION_ROOT',validation.db_path().parent/'production')))


def apply_models():
    with closing(engine().connect()) as c:
        row=c.execute("SELECT value FROM settings WHERE name='models'").fetchone()
    if row:
        for key,value in json.loads(row[0]).items():os.environ[key]=value


def save_models(data):
    current=capabilities();available=current['text'].get('models',[])
    selected={}
    for field,var in [('text','PRODUCTION_TEXT_MODEL'),('embedding','PRODUCTION_EMBED_MODEL'),('vision','PRODUCTION_VISION_MODEL')]:
        value=data.get(field,'')
        if value and value not in available:raise ValueError('Choose an installed local model')
        selected[var]=value
    with closing(engine().connect()) as c,c:
        c.execute("INSERT INTO settings VALUES('models',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(json.dumps(selected),))
    apply_models();return {'saved':True,'paid_fallbacks':False}


def submit(data):
    spec=dict(data['spec']);keyword=spec.get('keyword','')
    selling_context=spec.get('research') or {}
    if not isinstance(selling_context,dict):raise ValueError('Research context must be an object')
    selling_context=selling_context.get('selling_products',selling_context)
    if not isinstance(selling_context,dict):raise ValueError('Selling-product context must be an object')
    from services.research_listing import current_candidate
    try:spec['research']=current_candidate(keyword)
    except ValueError:spec['research']={'status':'unvalidated_operator_concept','keyword':keyword,'qualification_credit':False}
    if selling_context.get('selling_opportunity'):
        from services.selling_products import production_intake
        intake=production_intake(selling_context['selling_opportunity'])
        if selling_context.get('evidence_fingerprint')!=intake['research']['evidence_fingerprint']:
            raise ValueError('Selling-product evidence changed. Reopen the reviewed brief before queuing production.')
        spec['research']['selling_products']=intake['research']
    job=engine().submit(spec,data.get('product_id'))
    mirror(job);return job


def mirror(job):
    # Generic revisioned records are already supported by the private mirror.
    previous=validation.records(job['product_id'],'project')
    spec=job['spec']
    private_v2 = spec.get('schema_version', 1) == 2
    project={'name':spec['family'].replace('_',' ').title() if private_v2 else spec['name'],'product_type':spec['family'],'keywords':[] if private_v2 else list(dict.fromkeys([spec['keyword'],*spec['supporting_keywords']]))[:15],
             'created_at':previous[0]['payload']['created_at'] if previous else validation.stamp(),
             'source':'production_engine','production_product_id':job['product_id']}
    validation.put('project',job['product_id'],project,job['product_id'])
    # Customer/order inputs must never be mirrored with catalog specifications.
    # V2 mirrors are deliberately allowlisted even if a caller embeds private data.
    mirrored = ({key:job.get(key) for key in ('id','product_id','revision','status','created_at','updated_at')}
                if private_v2 else job)
    if private_v2:
        mirrored['schema_version']=2
        mirrored['family']=spec['family']
        mirrored['private_details_omitted']=True
    validation.put('production_job',job['product_id'],mirrored,'production:'+job['id'])


def renderer_capabilities():
    try:
        from etgen_production.capabilities import registry as registered
        return registered()
    except ImportError:
        return {'status':'engine_upgrade_required','families':[],
                'message':'Install the verified product-line engine to enable these builders.'}


def customer_store():
    try:
        from etgen_production.customers import CustomerStore
    except ImportError as exc:
        raise ValueError('Install the verified engine with private customer intake support') from exc
    return CustomerStore(engine())


def launch_recipes():
    try:
        from services.production_recipes import recipes
    except ImportError as exc:
        raise ValueError('Install the verified product-line engine for starter briefs') from exc
    return {'recipes':recipes(), 'research_status':'unvalidated_operator_concept',
            'qualification_credit':False, 'automatic_activation':False}


def overview():
    return {**engine().status(),'capabilities':capabilities(),'renderers':renderer_capabilities(),
            'models':{key:os.getenv(var,'') for key,var in [('text','PRODUCTION_TEXT_MODEL'),('embedding','PRODUCTION_EMBED_MODEL'),('vision','PRODUCTION_VISION_MODEL')]}}


class Worker:
    def __init__(self):self.task=None;self.stopping=False;self.last_outcome='idle';self.last_research=0
    async def run(self):
        while not self.stopping:
            try:
                if time.monotonic()-self.last_research>60 and not engine().status()['paused']:
                    from services.research_listing import overview as supported
                    created=await asyncio.to_thread(engine().enqueue_research,supported().get('candidates',[]))
                    for job in created:await asyncio.to_thread(mirror,job)
                    self.last_research=time.monotonic()
                result=await asyncio.to_thread(engine().tick)
                if result:
                    await asyncio.to_thread(mirror,result)
                    await asyncio.to_thread(validation.retry_sync)
                self.last_outcome=result['status'] if result else 'idle'
            except Exception:
                self.last_outcome='failed_preserved_for_retry'
            await asyncio.sleep(5)
    def start(self):apply_models();self.task=asyncio.create_task(self.run())
    async def stop(self):
        self.stopping=True
        # An already committing operation finishes; process termination is handled by leases.
        if self.task:
            try:await asyncio.wait_for(asyncio.shield(self.task),timeout=10)
            except asyncio.TimeoutError:pass


def match(data):
    spec=data['spec'];candidates=data.get('candidates',[])
    if not isinstance(candidates,list) or len(candidates)>200:raise ValueError('At most 200 private candidates can be matched')
    return related(spec,candidates)
