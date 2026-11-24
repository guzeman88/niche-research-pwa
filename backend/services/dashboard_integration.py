"""Service-only aggregate publisher with allowlisted operator startup headers.
Never exports raw evidence, customer inputs, artwork or credentials in its payload.
"""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import base64
import hashlib
import json
import os
import sqlite3
import re
import subprocess
import threading
import time
import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def now():
    return datetime.now(timezone.utc).isoformat()


def native_database():
    from pipeline import keyword_database as kdb
    manifest = Path(os.environ.get('APP_KEYWORD_FEED_ROOT', '')) / 'installation.json'
    if manifest.is_file():
        return Path(json.loads(manifest.read_text())['database'])
    return kdb.DB_PATH


def connection(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    deadline = time.monotonic() + 25
    con.set_progress_handler(lambda: time.monotonic() > deadline, 100000)
    return con


def canonical_domain(value):
    raw = str(value or 'unknown').strip().lower().replace(' ', '_')
    return {'professionals': 'professions', 'proffessions': 'professions',
            'aesthetic': 'aesthetics', 'home_decor': 'home_decor_themes',
            'occasion_holidays': 'occasions_holidays', 'products_types': 'pod_product_types',
            'product_types': 'pod_product_types', 'product_type': 'pod_product_types', 'pet': 'pets'}.get(raw, raw)


def research_summary(path):
    with closing(connection(path)) as con:
        con.execute('BEGIN')
        total = con.execute('SELECT count(*) FROM seeds').fetchone()[0]
        quality = dict(con.execute("""SELECT count(*) attempted,
            coalesce(sum(evidence_status != 'failed' AND (evidence_status IN ('partial','verified') OR sources_json NOT IN ('[]','','null'))),0) successful,
            coalesce(sum(evidence_status='verified'),0) evidence_backed,
            coalesce(sum(evidence_status='failed'),0) failed,
            coalesce(sum(evidence_status='unverified' AND sources_json IN ('[]','','null')),0) no_data,
            coalesce(sum(julianday(last_collected_at)<julianday('now','-30 days')),0) stale,
            max(last_collected_at) latest FROM keyword_collection_state""").fetchone())
        domains = {}
        for row in con.execute('SELECT domain,count(*) cnt FROM seeds GROUP BY domain'):
            key = canonical_domain(row['domain']); domains[key] = domains.get(key, 0) + row['cnt']
        scores = [dict(r) for r in con.execute("""SELECT s.keyword,s.opportunity_score AS score FROM scans s
            JOIN (SELECT keyword,max(id) id FROM scans WHERE score_version IS NOT NULL AND evidence_status='verified' GROUP BY keyword) latest
            ON s.id=latest.id WHERE s.opportunity_score IS NOT NULL""")]
        gap_count = con.execute("SELECT count(*) FROM gap_reports WHERE score_version IS NOT NULL AND evidence_status='verified' AND composite_gap_score IS NOT NULL").fetchone()[0]
        gap_avg = con.execute("SELECT avg(composite_gap_score) FROM gap_reports WHERE score_version IS NOT NULL AND evidence_status='verified'").fetchone()[0]
        sources = [dict(r) for r in con.execute('SELECT source,count(*) rows,count(distinct keyword) keywords,max(observed_at) latest FROM keyword_observations GROUP BY source')]
        latest = quality.pop('latest')
        stats = {**quality, 'total_seeds': total, 'scanned': quality['attempted'],
            'unscanned': max(0, total-quality['attempted']), 'total_scans': con.execute('SELECT count(*) FROM scans').fetchone()[0],
            'coverage_pct': round(100*quality['attempted']/total, 1) if total else None,
            'avg_opportunity': round(sum(r['score'] for r in scores)/len(scores),1) if scores else None,
            'avg_gap_score': round(gap_avg,1) if gap_avg is not None else None,
            'breakout_count': None, 'expansion_edges': con.execute('SELECT count(*) FROM expansion_tree').fetchone()[0],
            'top_gap_keyword': None, 'domains': [{'domain': k,'cnt': v} for k,v in sorted(domains.items(), key=lambda r:(-r[1],r[0]))]}
        buckets = [{'label': label, 'count': sum(low <= r['score'] < high for r in scores)}
                   for low,high,label in [(0,20,'0–19'),(20,40,'20–39'),(40,60,'40–59'),(60,80,'60–79'),(80,101,'80–100')]]
        market = next((r for r in sources if r['source']=='etsy_marketplace_insights'), {})
        evidence = {'versioned_scores': len(scores), 'versioned_gaps': gap_count,
            'marketplace_insights_rows': market.get('rows',0), 'marketplace_insights_keywords': market.get('keywords',0),
            'shop_stats_rows': next((r['rows'] for r in sources if r['source']=='etsy_shop_stats'),0)}
        return {'stats':stats,'evidence':evidence,'source_watermarks':{'latest_collection_at': latest},
                'sources':sources,'score_distribution':buckets,'research_leads':sorted(scores,key=lambda r:-r['score'])[:8],
                'breakouts':{'status':'not_available','items':[],'reason':'A comparable-window trend detector has not been validated.'}}


def build_snapshot():
    from services import product_validation as ledger, keyword_feed_status
    from services.sales_intelligence import store
    data = research_summary(native_database())
    feed = keyword_feed_status.status()
    try:
        counts = store.counts()
        intelligence = {k: counts.get(k) for k in ('listings','reference_listings','observations','outcomes','models','predictions','paused','automatic_estimator')}
        # Worker controls are reduced to counts; no IDs, raw packets or credentials.
        intelligence['automatic_estimator'] = {k:counts.get('automatic_estimator',{}).get(k) for k in ('at','tracked','estimated','statuses')}
        intelligence['status'] = 'provisional_estimates_not_verified_sales'
    except Exception:
        intelligence = {'status':'unavailable'}
    with closing(connection(ledger.db_path())) as con:
        records = con.execute('SELECT count(*) FROM records').fetchone()[0]
        projects = con.execute("SELECT count(*) FROM records WHERE kind='project'").fetchone()[0]
    from services.production import launch_recipes
    recipes=len(launch_recipes()['recipes'])
    production = {'status':'unavailable','jobs':None,'review_queue':None,'starting_recipes':recipes}
    path = Path(os.environ.get('PRODUCTION_ROOT', ledger.db_path().parent/'production'))/'production.sqlite'
    if path.is_file():
        with closing(connection(path)) as con:
            statuses = {r[0]:r[1] for r in con.execute('SELECT status,count(*) FROM jobs GROUP BY status')}
            production = {'status':'connected','jobs':sum(statuses.values()),'statuses':statuses,
                'review_queue':sum(v for k,v in statuses.items() if k in ('review','awaiting_review','needs_review')),'starting_recipes':recipes}
    supported = {'status':'not_initialized'}
    feed_root = native_database()
    if feed_root.is_file():
        from services import supported_keywords
        with closing(connection(feed_root)) as con:
            value = supported_keywords.overview(con, limit=8)
            supported = {k:value[k] for k in ('status','target','qualified_this_month','baseline_groups','available_supported_groups','etsy_demand_backed_groups','as_of') if k in value}
    from services.storage_health import storage_state
    data['storage']=storage_state(native_database(),ledger.db_path())
    from services.startup import summary as startup_summary
    data['startup']=startup_summary()
    data.update(schema_version=2, generated_at=now(), snapshot_version=int(time.time()*1000),
        data_status='degraded' if feed.get('status') not in ('completed','ok') else 'healthy',
        feed={k:feed.get(k) for k in ('status','last_attempt','last_completed','last_success','errors','optimization')},
        coverage={k:feed.get('coverage',{}).get(k) for k in ('as_of','library_keywords','active_keywords','exploration_keywords','active_current_competition','active_google_monthly_direct','active_google_monthly_supported','active_paired_keywords','providers')},
        intelligence=intelligence,production=production,validation={'records':records,'projects':projects},supported=supported,
        scope='native_collection_library',providers=[],duration_ms=0)
    data['input_fingerprint']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    return data


def validate_snapshot(data):
    stats=data.get('stats',{})
    def count(value):return isinstance(value,int) and not isinstance(value,bool) and value>=0
    if not count(stats.get('total_seeds')):raise ValueError('Invalid library count')
    for key in ('attempted','successful','evidence_backed','failed','no_data','stale','scanned','total_scans'):
        if key in stats and not count(stats[key]):raise ValueError('Invalid measured count')
    if stats.get('scanned',0)>stats['total_seeds']:raise ValueError('Mixed library scopes')
    domains=stats.get('domains',[])
    if any(not count(row.get('cnt')) for row in domains) or sum(row['cnt'] for row in domains)!=stats['total_seeds']:
        raise ValueError('Category counts do not match library scope')
    for source in data.get('sources',[]):
        if not count(source.get('keywords')) or not count(source.get('rows')) or source['keywords']>source['rows']:
            raise ValueError('Invalid source counts')


def seal_credential(token, secret):
    key=base64.b64decode(secret,validate=True)
    if len(key)!=32: raise ValueError('Invalid bridge encryption configuration')
    nonce=os.urandom(12)
    encrypted=AESGCM(key).encrypt(nonce,json.dumps({'token':token}).encode(),b'private-backend')
    return base64.urlsafe_b64encode(nonce+encrypted[-16:]+encrypted[:-16]).decode().rstrip('=')


class Worker:
    """Report work cannot delay availability; only verified connectors are advertised."""
    def __init__(self):
        self.task=None; self.connection_task=None; self.process=None; self.endpoint=None
        self.stopping=False; self.failures=0; self.last_restart=0.0
        self.lock=threading.RLock()
        self.state={'enabled':True,'status':'starting','connection_status':'starting','private_connection':False}

    def update(self, **values):
        with self.lock:self.state={**self.state,**values}

    def start(self):
        self.task=asyncio.create_task(self.run())
        self.connection_task=asyncio.create_task(self.run_connection())

    def terminate_connector(self):
        # Only the process created by this worker; never find/kill a process by port.
        with self.lock:
            process=self.process; self.process=None; self.endpoint=None
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(10)
            except subprocess.TimeoutExpired:process.kill(); process.wait(5)
        if process and process.stdout:process.stdout.close()

    async def stop(self):
        self.stopping=True
        for task in (self.task,self.connection_task):
            if task:task.cancel()
        for task in (self.task,self.connection_task):
            if task:
                try:await task
                except asyncio.CancelledError:pass
        await asyncio.to_thread(self.terminate_connector)

    def tunnel(self):
        with self.lock:
            if self.stopping or os.environ.get('APP_DASHBOARD_TUNNEL_ENABLED')!='1':return
            if self.process and self.process.poll() is None:return
            if len(os.environ.get('PIPELINE_API_TOKEN',''))<40 or not os.environ.get('DASHBOARD_BRIDGE_SECRET'):
                raise ValueError('Configure private access before exposing the API')
            self.endpoint=None
            binary=os.environ.get('CLOUDFLARED_PATH','')
            if not Path(binary).is_file():raise ValueError('Configured connector is missing')
            self.process=subprocess.Popen([binary,'tunnel','--no-autoupdate','--url','http://127.0.0.1:18020','--protocol','http2'],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            process=self.process
        def observe():
            try:
                for line in process.stdout:
                    match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
                    with self.lock:
                        if match and self.process is process and not self.stopping:self.endpoint=match[0]
            except (ValueError,OSError):pass  # Owned pipe closed during shutdown/recovery.
        threading.Thread(target=observe,daemon=True).start()

    def reporting_client(self):
        url=os.environ['REPORTING_SUPABASE_URL'].rstrip('/')
        if not url.startswith('https://'):raise ValueError('Reporting requires HTTPS')
        key=os.environ['REPORTING_SUPABASE_SERVICE_ROLE_KEY']
        return url,httpx.Client(timeout=12,headers={'apikey':key,'Authorization':'Bearer '+key,'Prefer':'resolution=merge-duplicates'})

    def heartbeat(self):
        error=None
        try:self.tunnel()
        except Exception as exc:error=type(exc).__name__
        with self.lock:
            endpoint=self.endpoint; process=self.process
        enabled=bool(not self.stopping and endpoint and process and process.poll() is None)
        auth_failure=False
        if enabled:
            try:
                response=httpx.get(endpoint+'/api/health/live',headers={'Authorization':'Bearer '+os.environ['PIPELINE_API_TOKEN']},timeout=8)
                auth_failure=response.status_code in (401,403)
                payload=response.json() if response.status_code==200 else {}
                enabled=response.status_code==200 and isinstance(payload,dict) and payload.get('status')=='ok'
                if not enabled:error='ConnectorAuthorization' if auth_failure else 'ConnectorHealth'
            except (httpx.HTTPError,ValueError):enabled=False;error='ConnectorUnavailable'
        self.failures=0 if enabled else self.failures+1
        # An alive-but-unreachable tunnel must recover too. Do not rotate on an
        # authorization failure or repeatedly restart during an Internet outage.
        if process and not enabled and not auth_failure and self.failures>=3 and time.monotonic()-self.last_restart>=120:
            try:
                local=httpx.get('http://127.0.0.1:18020/api/health/live',headers={'Authorization':'Bearer '+os.environ['PIPELINE_API_TOKEN']},timeout=3)
                if local.status_code==200 and not self.stopping:
                    self.last_restart=time.monotonic();self.terminate_connector();self.tunnel()
            except httpx.HTTPError:pass
        # Never revive readiness from a late request after shutdown begins.
        if self.stopping:return
        url,client=self.reporting_client()
        with client:
            bridge={'id':'active','updated_at':now(),'enabled':enabled,'endpoint':endpoint if enabled else None,
                'credential':seal_credential(os.environ['PIPELINE_API_TOKEN'],os.environ['DASHBOARD_BRIDGE_SECRET']) if enabled else None}
            response=client.post(url+'/rest/v1/app_backend_connections',json=bridge);response.raise_for_status()
        self.update(connection_status='connected' if enabled else 'reconnecting',private_connection=enabled,
            heartbeat_at=bridge['updated_at'],connection_error=error)

    def publish(self):
        data=build_snapshot()
        validate_snapshot(data)
        if self.stopping:return
        with self.lock:
            connected=bool(self.state.get('private_connection'))
        data['connection']={'private_actions_available':connected,'status':'connected' if connected else 'reconnecting'}
        data.pop('input_fingerprint',None)
        data['input_fingerprint']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        row={'id':'active','snapshot_version':data['snapshot_version'],'generated_at':data['generated_at'],
            'input_fingerprint':data['input_fingerprint'],'payload':data}
        url,client=self.reporting_client()
        with client:
            response=client.post(url+'/rest/v1/app_dashboard_state',json=row);response.raise_for_status()
        self.update(status='connected',published_at=data['generated_at'],report_error=None)

    async def run_connection(self):
        while not self.stopping:
            started=time.monotonic()
            work=asyncio.create_task(asyncio.to_thread(self.heartbeat))
            try:await asyncio.shield(work)
            except asyncio.CancelledError:
                # Finish a bounded in-flight heartbeat before terminating its route.
                try:await work
                except Exception:pass
                raise
            except Exception as exc:self.update(connection_status='reconnecting',connection_error=type(exc).__name__)
            await asyncio.sleep(max(1,20-(time.monotonic()-started)))

    async def run(self):
        while not self.stopping:
            try:await asyncio.to_thread(self.publish)
            except asyncio.CancelledError:raise
            except Exception as exc:self.update(status='needs_attention',report_error=type(exc).__name__)
            await asyncio.sleep(60)


def configured_worker():
    if os.environ.get('APP_DASHBOARD_REPORTING_ENABLED')!='1':return None
    if not all(os.environ.get(k) for k in ('REPORTING_SUPABASE_URL','REPORTING_SUPABASE_SERVICE_ROLE_KEY')):return None
    return Worker()
