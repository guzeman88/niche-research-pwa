import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import sqlite3
import threading
from types import SimpleNamespace
import pytest
from services import dashboard_integration as bridge


class Process:
    stdout=None
    stopped=False
    def poll(self):return 0 if self.stopped else None
    def terminate(self):self.stopped=True
    def wait(self,*_):return 0


class Response:
    def __init__(self,status=200):self.status_code=status
    def json(self):return {'status':'ok'}
    def raise_for_status(self):pass


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv('PIPELINE_API_TOKEN','s'*64)
    monkeypatch.setenv('DASHBOARD_BRIDGE_SECRET',base64.b64encode(b'k'*32).decode())
    w=bridge.Worker();w.process=Process();w.endpoint='https://fixture.trycloudflare.com'
    posts=[]
    class Client:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def post(self,url,json):posts.append((url,json));return Response()
    monkeypatch.setattr(w,'reporting_client',lambda:('https://reporting.test',Client()))
    monkeypatch.setattr(w,'tunnel',lambda:None)
    monkeypatch.setattr(bridge.httpx,'get',lambda *_a,**_kw:Response())
    return w,posts


def snapshot():
    return {'schema_version':2,'snapshot_version':12,'generated_at':datetime.now(timezone.utc).isoformat(),
            'stats':{'total_seeds':2,'scanned':1,'attempted':1,'domains':[{'domain':'fixture','cnt':2}]},
            'sources':[{'source':'fixture','keywords':1,'rows':2}]}


def test_heartbeat_continues_while_report_is_blocked_and_fails(worker,monkeypatch):
    w,posts=worker;started=threading.Event();release=threading.Event()
    def blocked():
        started.set();release.wait(2);raise sqlite3.OperationalError('fixture report failure')
    monkeypatch.setattr(bridge,'build_snapshot',blocked)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future=pool.submit(w.publish)
        try:
            assert started.wait(1)
            w.heartbeat()
            assert not future.done()
            assert len(posts)==1 and posts[0][0].endswith('/app_backend_connections')
            assert posts[0][1]['enabled'] is True
        finally:release.set()
        with pytest.raises(sqlite3.OperationalError):future.result()
    assert w.state['private_connection'] is True


def test_bad_report_never_overwrites_last_success_or_disables_connection(worker,monkeypatch):
    w,posts=worker;bad=snapshot();bad['stats']['scanned']=3
    monkeypatch.setattr(bridge,'build_snapshot',lambda:bad)
    with pytest.raises(ValueError,match='scopes'):w.publish()
    assert posts==[]
    w.heartbeat();assert posts[-1][1]['enabled'] is True


def test_atomic_report_has_consistent_fingerprint_and_unknowns(worker,monkeypatch):
    w,posts=worker;data=snapshot();data['stats']['avg_opportunity']=None
    monkeypatch.setattr(bridge,'build_snapshot',lambda:data)
    w.heartbeat();w.publish()
    row=posts[-1][1]
    assert row['payload']['connection']['private_actions_available'] is True
    assert row['input_fingerprint']==row['payload']['input_fingerprint']
    assert row['payload']['stats']['avg_opportunity'] is None


def test_late_probe_cannot_restore_readiness_after_shutdown(worker,monkeypatch):
    w,posts=worker
    def probe(*_a,**_kw):w.stopping=True;return Response()
    monkeypatch.setattr(bridge.httpx,'get',probe)
    w.heartbeat();assert posts==[]


def test_alive_unreachable_connector_recovers_with_cooldown(worker,monkeypatch):
    w,posts=worker;old=w.process;restarts=[]
    monkeypatch.setattr(bridge.time,'monotonic',lambda:500)
    monkeypatch.setattr(bridge.httpx,'get',lambda url,**_kw:Response(200 if '127.0.0.1' in url else 503))
    def tunnel():
        if w.process is None:w.process=Process();w.endpoint='https://replacement.trycloudflare.com';restarts.append(True)
    monkeypatch.setattr(w,'tunnel',tunnel)
    for _ in range(6):w.heartbeat()
    assert old.stopped and len(restarts)==1
    assert all(not row['enabled'] for _,row in posts)


def test_authorization_failure_does_not_rotate_connector(worker,monkeypatch):
    w,posts=worker;old=w.process
    monkeypatch.setattr(bridge.httpx,'get',lambda *_a,**_kw:Response(401))
    for _ in range(4):w.heartbeat()
    assert not old.stopped
    assert posts[-1][1]['enabled'] is False
    assert w.state['connection_error']=='ConnectorAuthorization'


def test_liveness_has_no_database_dependency(monkeypatch):
    import asyncio
    from main import api_liveness
    from pipeline import keyword_database as kdb
    monkeypatch.setattr(kdb,'has_seeds',lambda:(_ for _ in ()).throw(AssertionError('Liveness touched database')))
    assert asyncio.run(api_liveness())['status']=='ok'


def test_started_worker_runs_heartbeat_independently_of_blocked_report(worker,monkeypatch):
    import asyncio
    w,posts=worker;entered=threading.Event();release=threading.Event()
    def blocked():entered.set();release.wait(2);raise sqlite3.OperationalError('fixture')
    monkeypatch.setattr(bridge,'build_snapshot',blocked)
    async def scenario():
        w.start()
        try:
            assert await asyncio.to_thread(entered.wait,1)
            for _ in range(100):
                if w.state['private_connection']:break
                await asyncio.sleep(.01)
            assert w.state['private_connection'] is True and posts
        finally:release.set();await w.stop()
    asyncio.run(scenario())
