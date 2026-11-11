from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import time
from jose import jwt
from starlette.requests import Request
from services.dashboard_integration import research_summary, seal_credential, configured_worker
from security import is_authorized


def test_summary_uses_same_library_scope_and_excludes_unversioned_scores(tmp_path):
    path=tmp_path/'native.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE seeds(keyword TEXT,domain TEXT);
        CREATE TABLE keyword_collection_state(keyword TEXT,evidence_status TEXT,sources_json TEXT,last_collected_at TEXT);
        CREATE TABLE scans(id INTEGER,keyword TEXT,opportunity_score REAL,score_version TEXT,evidence_status TEXT);
        CREATE TABLE gap_reports(composite_gap_score REAL,score_version TEXT,evidence_status TEXT);
        CREATE TABLE keyword_observations(keyword TEXT,source TEXT,observed_at TEXT);
        CREATE TABLE expansion_tree(parent TEXT);
        INSERT INTO seeds VALUES('one','professionals'),('two','professions'),('three','pets');
        INSERT INTO keyword_collection_state VALUES('one','verified','["etsy"]','2026-11-11T00:00:00Z');
        INSERT INTO scans VALUES(1,'one',99,NULL,'verified'),(2,'two',85,'v1','verified'),(3,'two',20,'v1','verified'),(4,'three',90,'v1','unverified');
        INSERT INTO keyword_observations VALUES('one','etsy_marketplace_insights','2026-11-11');
        ''')
    data=research_summary(path)
    assert data['stats']['total_seeds']==3
    assert data['stats']['attempted']==1
    assert data['stats']['coverage_pct']==33.3
    assert data['stats']['avg_opportunity']==20
    assert sum(r['cnt'] for r in data['stats']['domains'])==3
    assert data['stats']['domains'][0]=={'domain':'professions','cnt':2}
    assert data['evidence']['versioned_scores']==1
    assert sum(r['count'] for r in data['score_distribution'])==1
    assert data['stats']['breakout_count'] is None
    assert data['breakouts']['status']=='not_available'
    assert configured_worker() is None


def request(path='/api/production', method='GET', token=''):
    return Request({'type':'http','method':method,'path':path,'query_string':b'',
        'server':('backend.example',443),'scheme':'https','client':('10.0.0.1',1234),
        'headers':[(b'authorization',('Bearer '+token).encode())]})


def test_delegated_access_is_short_lived_and_bound_to_method_and_resource(monkeypatch):
    secret='x'*64;monkeypatch.setenv('PIPELINE_API_TOKEN',secret)
    at=int(time.time())
    claims={'iss':'etgen-account-bridge','aud':'etgen-private-api','sub':'admin-fixture',
        'iat':at,'exp':at+30,'method':'GET','path':'/api/production'}
    token=jwt.encode(claims,secret,algorithm='HS256')
    assert is_authorized(request(token=token))
    assert not is_authorized(request(method='POST',token=token))
    assert not is_authorized(request(path='/api/settings',token=token))
    for changes in ({'exp':at-1},{'exp':at+300},{'aud':'other'},{'iss':'other'},{'iat':at+20,'exp':at+30}):
        assert not is_authorized(request(token=jwt.encode({**claims,**changes},secret,algorithm='HS256')))
    assert not is_authorized(request(token=token+'tampered'))


def test_bridge_credentials_are_encrypted_and_context_bound():
    import base64
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    secret=base64.b64encode(b'k'*32).decode()
    sealed=seal_credential('private-test-token',secret)
    assert 'private-test-token' not in sealed
    raw=base64.urlsafe_b64decode(sealed+'='*(-len(sealed)%4))
    value=AESGCM(b'k'*32).decrypt(raw[:12],raw[28:]+raw[12:28],b'private-backend')
    assert json.loads(value)=={'token':'private-test-token'}


def test_keyword_search_and_paging_cover_the_full_library(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pipeline import keyword_database as kdb
    from routers import dashboard
    path=tmp_path/'keywords.sqlite'
    monkeypatch.setattr(kdb,'DB_PATH',path);kdb.init_db()
    with sqlite3.connect(path) as db:
        db.executemany('INSERT INTO seeds(keyword,domain,source,added_at) VALUES(?,?,?,?)',
            [(f'early {i:05}','fixture','test','2026-11-11') for i in range(15010)]+[('zebra beyond first page','fixture','test','2026-11-11')])
    monkeypatch.setattr(dashboard,'native_database',lambda:path)
    app=FastAPI();app.include_router(dashboard.router)
    with TestClient(app) as client:
        found=client.get('/api/dashboard/keywords',params={'q':'zebra'}).json()
        assert found['total']==1 and found['items'][0]['keyword']=='zebra beyond first page'
        page=client.get('/api/dashboard/keywords',params={'limit':100,'offset':15000}).json()
        assert page['total']==15011 and len(page['items'])==11
        assert client.get('/api/dashboard/keywords',params={'sort':'keyword;DELETE'}).status_code==422
        assert client.get('/api/dashboard/keywords',params={'q':'%'}).json()['total']==0


def test_connector_mode_protects_even_research_gets(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from security import protect_operator_api
    monkeypatch.setenv('APP_DASHBOARD_TUNNEL_ENABLED','1')
    monkeypatch.setenv('SUPABASE_URL','http://127.0.0.1:9')
    app=FastAPI();app.middleware('http')(protect_operator_api)
    @app.get('/api/stats')
    def stats():return {'fixture':True}
    with TestClient(app) as client:
        assert client.get('/api/stats').status_code==401
