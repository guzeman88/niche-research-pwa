"""Private production API and additive mirror integration, isolated from real data."""
from contextlib import closing
import sqlite3
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security import protect_operator_api
from routers.production import router
from services import production,product_validation
from etgen_production.engine import REVIEW_CHECKS


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('PRODUCTION_ROOT',str(tmp_path/'production'))
    monkeypatch.setenv('VALIDATION_DB_PATH',str(tmp_path/'ledger.sqlite'))
    monkeypatch.setenv('SUPABASE_URL','');monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','')
    monkeypatch.setattr('services.research_listing.current_candidate',lambda _: (_ for _ in ()).throw(ValueError('unqualified')))
    app=FastAPI();app.middleware('http')(protect_operator_api);app.include_router(router)
    return TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',12345))


def spec():
    return {'name':'Weekly Work Planner','keyword':'work planner','buyer':'Workers planning their week',
            'purpose':'Organize daily priorities and appointments using printable writing areas.',
            'family':'planner','content':['Monday','Tuesday'],'price':8,'unit_cost':1,
            'delivery':'Download PDF files after purchase. Contact seller for support.',
            'rights_note':'Original authored content and template.','category_id':123,
            'tags':['work planner','daily planner','weekly planner','work week','work notes','daily notes',
                    'planner pages','planning pdf','planner download','priority planner','work priorities','daily schedule','work schedule']}


def test_private_reads_and_writes(setup):
    assert setup.get('/api/production',headers={'Origin':'https://untrusted.example'}).status_code==401
    assert setup.post('/api/production/jobs',json={'spec':spec()},headers={'Origin':'https://untrusted.example'}).status_code==401
    assert setup.get('/api/production').status_code==200


def test_optional_engine_omission_keeps_backend_running(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    env={k:v for k,v in os.environ.items() if not k.startswith(('SUPABASE_','ETSY_','GOOGLE_ADS_','APP_'))}
    env.update(BACKEND_DIR=str(tmp_path),VALIDATION_DB_PATH=str(tmp_path/'ledger.sqlite'),
               AUTO_START_SCHEDULER='0',APP_PRODUCTION_ENABLED='0',APP_KEYWORD_FEED_ENABLED='0',
               SUPABASE_URL='',SUPABASE_SERVICE_ROLE_KEY='',SUPABASE_ANON_KEY='')
    code="""
import importlib.abc,sys
class MissingEngine(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='etgen_production':raise ModuleNotFoundError('isolated missing engine',name=fullname)
sys.meta_path.insert(0,MissingEngine())
from fastapi.testclient import TestClient
from main import app
with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',123)) as client:
 assert client.get('/api/health').status_code==200
 assert client.get('/api/product-validation').status_code==200
 assert client.get('/api/production').status_code==503
"""
    subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],env=env,
                   check=True,capture_output=True,timeout=30)


def test_actual_production_review_and_export(setup):
    response=setup.post('/api/production/jobs',json={'spec':spec()});assert response.status_code==201,response.text
    job=response.json();assert job['spec']['research']['status']=='unvalidated_operator_concept'
    rendered=production.engine().tick();production.mirror(rendered)
    assert rendered['status']=='needs_review'
    assert setup.get(f'/api/production/jobs/{job["id"]}/files/customer.pdf').content.startswith(b'%PDF')
    assert setup.post(f'/api/production/jobs/{job["id"]}/export').status_code==400
    review={'revision':rendered['revision'],'artifact_fingerprint':rendered['result']['manifest']['artifact_fingerprint'],
            'decision':'approve','note':'Inspected the actual files, rights and product facts.', 'checks':{k:True for k in REVIEW_CHECKS}}
    assert setup.post(f'/api/production/jobs/{job["id"]}/review',json=review).status_code==200
    exported=setup.post(f'/api/production/jobs/{job["id"]}/export');assert exported.status_code==200
    assert exported.json()['publication_performed'] is False
    assert len(product_validation.records(kind='production_job'))==1
    assert len(product_validation.records(kind='project'))==1
    assert product_validation.records(kind='project')[0]['payload']['source']=='production_engine'


def test_provider_and_profile_gates(setup,monkeypatch):
    data=spec();data['concept_method']='local_model'
    assert setup.post('/api/production/profiles',json={'spec':data,'enabled':True,'facts_reviewed':False}).status_code==400
    assert setup.post('/api/production/profiles',json={'spec':data,'enabled':False,'facts_reviewed':True}).status_code==200
    assert setup.get('/api/production/training-dataset').json()['training_started'] is False
    assert setup.post('/api/production/assets',json={'base64':'invalid','license_note':'Original authored source.'}).status_code==400
