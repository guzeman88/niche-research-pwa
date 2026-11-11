"""Opt-in bounded aggregate publisher. Never collects evidence or exports private records."""
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
    data.update(schema_version=2, generated_at=now(), snapshot_version=int(time.time()*1000),
        data_status='degraded' if feed.get('status') not in ('completed','ok') else 'healthy',
        feed={k:feed.get(k) for k in ('status','last_attempt','last_completed','last_success','errors','optimization')},
        coverage={k:feed.get('coverage',{}).get(k) for k in ('as_of','library_keywords','active_keywords','exploration_keywords','active_current_competition','active_google_monthly_direct','active_google_monthly_supported','active_paired_keywords','providers')},
        intelligence=intelligence,production=production,validation={'records':records,'projects':projects},supported=supported,
        scope='native_collection_library',providers=[],duration_ms=0)
    data['input_fingerprint']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    return data


def seal_credential(token, secret):
    key=base64.b64decode(secret,validate=True)
    if len(key)!=32: raise ValueError('Invalid bridge encryption configuration')
    nonce=os.urandom(12)
    encrypted=AESGCM(key).encrypt(nonce,json.dumps({'token':token}).encode(),b'private-backend')
    return base64.urlsafe_b64encode(nonce+encrypted[-16:]+encrypted[:-16]).decode().rstrip('=')


class Worker:
    def __init__(self):
        self.task=None;self.process=None;self.endpoint=None;self.stopping=False;self.state={'enabled':True,'status':'starting'}
    def start(self):
        self.task=asyncio.create_task(self.run())
    async def stop(self):
        self.stopping=True
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: await asyncio.to_thread(self.process.wait,10)
            except subprocess.TimeoutExpired: self.process.kill()
    def tunnel(self):
        if self.stopping:return
        if os.environ.get('APP_DASHBOARD_TUNNEL_ENABLED')!='1': return
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
            for line in process.stdout:
                match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
                if match and self.process is process:self.endpoint=match[0]
        threading.Thread(target=observe,daemon=True).start()
    def publish(self):
        connector_error=None
        try:self.tunnel()
        except Exception as exc:connector_error=type(exc).__name__
        data=build_snapshot()
        url=os.environ['REPORTING_SUPABASE_URL'].rstrip('/')
        key=os.environ['REPORTING_SUPABASE_SERVICE_ROLE_KEY']
        if not url.startswith('https://'): raise ValueError('Reporting requires HTTPS')
        with httpx.Client(timeout=20,headers={'apikey':key,'Authorization':'Bearer '+key,'Prefer':'resolution=merge-duplicates'}) as client:
            enabled=bool(not self.stopping and self.endpoint and self.process and self.process.poll() is None)
            if enabled:
                try:
                    # Verify the route and authorization before advertising readiness.
                    response=httpx.get(self.endpoint+'/api/health',headers={'Authorization':'Bearer '+os.environ['PIPELINE_API_TOKEN']},timeout=10)
                    enabled=response.status_code==200
                except httpx.HTTPError:enabled=False
            data['connection']={'private_actions_available':enabled,'status':'connected' if enabled else 'offline','error':connector_error}
            row={'id':'active','snapshot_version':data['snapshot_version'],'generated_at':data['generated_at'],
                 'input_fingerprint':data['input_fingerprint'],'payload':data}
            response=client.post(url+'/rest/v1/app_dashboard_state',json=row);response.raise_for_status()
            bridge={'id':'active','updated_at':now(),'enabled':enabled,'endpoint':self.endpoint if enabled else None,
                'credential':seal_credential(os.environ['PIPELINE_API_TOKEN'],os.environ['DASHBOARD_BRIDGE_SECRET']) if enabled else None}
            response=client.post(url+'/rest/v1/app_backend_connections',json=bridge);response.raise_for_status()
        self.state={'enabled':True,'status':'connected','published_at':data['generated_at'],'private_connection':enabled}
    async def run(self):
        while True:
            try: await asyncio.to_thread(self.publish)
            except asyncio.CancelledError: raise
            except Exception as exc:self.state={'enabled':True,'status':'needs_attention','error':type(exc).__name__}
            await asyncio.sleep(60)


def configured_worker():
    if os.environ.get('APP_DASHBOARD_REPORTING_ENABLED')!='1':return None
    if not all(os.environ.get(k) for k in ('REPORTING_SUPABASE_URL','REPORTING_SUPABASE_SERVICE_ROLE_KEY')):return None
    return Worker()
