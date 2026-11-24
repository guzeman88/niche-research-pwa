import hashlib
import json
import sqlite3
from io import BytesIO
from pathlib import Path
from contextlib import closing
import pytest
from fastapi import HTTPException
from PIL import Image
from services import startup


def setup_databases(tmp_path,monkeypatch):
    ledger=tmp_path/'validation.sqlite';production=tmp_path/'production';production.mkdir()
    monkeypatch.setenv('VALIDATION_DB_PATH',str(ledger));monkeypatch.setenv('PRODUCTION_ROOT',str(production))
    at='2026-11-24T15:00:00+00:00'
    with closing(sqlite3.connect(ledger)) as con,con:
        con.execute('CREATE TABLE records(id TEXT,kind TEXT,project_id TEXT,payload TEXT,updated_at TEXT)')
        con.executemany('INSERT INTO records VALUES(?,?,?,?,?)',[
            ('p','project','p',json.dumps({'name':'Binder','product_type':'planner'}),at),
            ('e','google','p',json.dumps({'raw':'PRIVATE-EVIDENCE'*200000}),at)])
    with closing(sqlite3.connect(production/'production.sqlite')) as con,con:
        con.executescript('CREATE TABLE jobs(id TEXT,product_id TEXT,revision TEXT,status TEXT,updated_at TEXT,created_at TEXT,result TEXT);CREATE TABLE specs(product_id TEXT,revision TEXT,payload TEXT);CREATE TABLE settings(name TEXT,value TEXT);')
        for version in (1,2):
            con.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',('j'+str(version),'p','r'+str(version),'needs_review',at,str(version),json.dumps({'manifest':{'render':{'previews':['preview.png']}},'private':'CUSTOMER-SECRET'})))
            con.execute('INSERT INTO specs VALUES(?,?,?)',('p','r'+str(version),json.dumps({'schema_version':version,'name':'CUSTOMER-SECRET' if version==2 else 'Binder','family':'wedding_binder','product_data':{'private':'CUSTOMER-SECRET'}})))
    return ledger,production/'production.sqlite'


def test_projection_is_read_only_bounded_latest_revision_and_private(tmp_path,monkeypatch):
    paths=setup_databases(tmp_path,monkeypatch)
    before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    monkeypatch.setattr(startup.validation,'summary',lambda *_:pytest.fail('Heavy evidence parser called'))
    data=startup.summary();encoded=json.dumps(data)
    assert len(encoded)<3000
    assert 'PRIVATE-EVIDENCE' not in encoded and 'CUSTOMER-SECRET' not in encoded
    assert data['projects']['total']==1 and data['projects']['projects'][0]['name']=='Binder'
    assert data['production']['total']==1
    assert data['production']['jobs'][0]['id']=='j2'
    assert data['production']['jobs'][0]['spec']['name']=='Wedding Binder'
    assert data['production']['human_approval_required'] is True
    assert before==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    assert data['input_fingerprint']==startup.summary()['input_fingerprint']


def test_missing_source_is_unknown_independently_and_never_creates_database(tmp_path,monkeypatch):
    ledger,production=setup_databases(tmp_path,monkeypatch)
    ledger.unlink()
    data=startup.summary()
    assert data['projects']['status']=='unavailable' and data['projects']['total'] is None
    assert data['projects']['projects'] is None and not ledger.exists()
    assert data['production']['status']=='ready'


def test_thumbnail_preserves_integrity_gate_and_size(tmp_path,monkeypatch):
    from routers import production
    path=tmp_path/'preview.png';Image.new('RGB',(1600,2000),'white').save(path)
    calls=[]
    class Engine:
        def job(self,_):return {'result':{'manifest':{'render':{'previews':['cover.png','inside.png']}}}}
        def file(self,job,name):calls.append((job,name));return path
    monkeypatch.setattr(production.service,'engine',Engine)
    response=production.thumbnail('j','inside')
    assert calls==[('j','inside.png')]
    with Image.open(BytesIO(response.body)) as image:assert image.size==(480,600) and image.format=='WEBP'
    assert len(response.body)<path.stat().st_size
    monkeypatch.setattr(Engine,'file',lambda *_:(_ for _ in ()).throw(ValueError('Corrupt package')))
    with pytest.raises(HTTPException):production.thumbnail('j','cover')


def test_startup_rejects_anonymous_remote_reads_and_scopes_tickets(monkeypatch):
    import asyncio,time,httpx
    from fastapi import FastAPI
    from jose import jwt
    from security import protect_operator_api
    from routers import startup as route
    app=FastAPI();app.middleware('http')(protect_operator_api);app.include_router(route.router)
    monkeypatch.setenv('PIPELINE_API_TOKEN','x'*64)
    monkeypatch.setattr(route,'summary',lambda:{'authorized':True})
    at=int(time.time())
    claims={'iss':'etgen-account-bridge','aud':'etgen-private-api','sub':'admin','iat':at,'exp':at+30,'method':'GET','path':'/api/startup'}
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('203.0.113.1',123)),base_url='https://backend.example') as client:
            assert (await client.get('/api/startup')).status_code in (401,403)
            token=jwt.encode(claims,'x'*64,algorithm='HS256')
            assert (await client.get('/api/startup',headers={'Authorization':'Bearer '+token})).json()=={'authorized':True}
            wrong=jwt.encode({**claims,'path':'/api/production'},'x'*64,algorithm='HS256')
            assert (await client.get('/api/startup',headers={'Authorization':'Bearer '+wrong})).status_code in (401,403)
    asyncio.run(check())
