"""Read-only, hourly aggregate of the canonical native library, never raw rows."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import threading
import time
import asyncio
import os
import sqlite3
import json
import hashlib

SPECS = {
    'etsy_listings':('keyword_listing_snapshots','etsy_open_api','observed_at'),
    'etsy_observations':('keyword_observations','etsy_open_api','observed_at'),
    'google_suggest':('keyword_suggestions','google_suggest','observed_at'),
    'google_trend_points':('keyword_trend_points','google_trends','collected_at'),
    'google_trend_observations':('keyword_observations','google_trends','observed_at'),
    'google_daily_observations':('keyword_observations','google_daily_trends','observed_at'),
    'pinterest_trend_points':('keyword_trend_points','pinterest_trends','collected_at'),
    'pinterest_observations':('keyword_observations','pinterest_trends','observed_at'),
    'reddit_observations':('keyword_observations','reddit_etsy','observed_at'),
    'etsy_marketplace_observations':('keyword_observations','etsy_marketplace_insights','observed_at'),
    'etsy_shop_observations':('keyword_observations','etsy_shop_stats','observed_at'),
    'google_planner_observations':('keyword_observations',('google_ads_keyword_planner','google_keyword_planner'),'observed_at'),
    'erank_observations':('keyword_observations','erank','observed_at'),
    'marmalead_observations':('keyword_observations','marmalead','observed_at'),
    'google_trends_csv_points':('keyword_trend_points','google_trends_csv','collected_at'),
    'google_trends_csv_observations':('keyword_observations','google_trends_csv','observed_at'),
}
_lock=threading.Lock()
_cache=None


def unavailable():
    return {'schema_version':1,'scope':'native_collection_library','generated_at':datetime.now(timezone.utc).isoformat(),
            'window_hours':24,'counts':{},'latest':{},'data_status':'unavailable','rate_basis':'observed_storage'}


def measure(path, at=None, stopping=None):
    at=at or datetime.now(timezone.utc)
    since=(at-timedelta(days=1)).isoformat()
    counts={};failed=[];sources={}
    con=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)
    con.row_factory=sqlite3.Row
    deadline=time.monotonic()+600
    con.set_progress_handler(lambda: time.monotonic()>deadline or bool(stopping and stopping.is_set()),10000)
    with closing(con):
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        for table,column in sorted({(t,c) for t,_,c in SPECS.values()}):
            providers=sorted({provider for name,(t,ps,_) in SPECS.items() if t==table for provider in (ps if isinstance(ps,tuple) else (ps,))})
            # One streaming aggregate per table. GROUP BY sorts millions of
            # input rows into a temporary B-tree, potentially on the system disk.
            # These fixed-source CASE aggregates need no sort or schema change.
            expressions=[];parameters=[]
            for i,provider in enumerate(providers):
                expressions.extend([f'count(case when source=? then 1 end) total_{i}',
                    f'count(case when source=? and julianday({column})>=julianday(?) and julianday({column})<=julianday(?) then 1 end) recent_{i}',
                    f'max(case when source=? then {column} end) latest_{i}'])
                parameters.extend([provider,provider,since,at.isoformat(),provider])
            try:
                row=con.execute('SELECT '+','.join(expressions)+' FROM '+table+' NOT INDEXED',parameters).fetchone()
                groups={provider:{'total':row[f'total_{i}'],'recent':row[f'recent_{i}'],'latest':row[f'latest_{i}']} for i,provider in enumerate(providers)}
                for name,(source_table,ps,_) in SPECS.items():
                    if source_table!=table:continue
                    ps=ps if isinstance(ps,tuple) else (ps,)
                    counts[name+'_total']=sum(groups[p]['total'] for p in ps)
                    counts[name+'_24h']=sum(groups[p]['recent'] for p in ps)
                    for provider in ps:
                        latest=groups[provider]['latest']
                        if latest:sources[provider]=max(sources.get(provider,''),latest)
            except sqlite3.Error:failed.append(table)
    return {'schema_version':1,'scope':'native_collection_library','generated_at':at.isoformat(),
            'window_start':since,'window_hours':24,'counts':counts,'latest':sources,
            'data_status':('partial' if counts else 'unavailable') if failed else 'complete','rate_basis':'observed_storage'}


def cache_path():
    from services.product_validation import db_path
    return db_path().parent/'public-collection-cache.json'


def source_identity(path):
    path=path.resolve();stat=path.stat()
    return hashlib.sha256(f'{path}|{stat.st_dev}|{stat.st_ino}'.encode()).hexdigest()


def read_cache(path):
    try:
        file=cache_path()
        if file.stat().st_size>64000:return None
        record=json.loads(file.read_text(encoding='utf-8'));value=record['data']
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(value['generated_at'])).total_seconds()
        if (record['source']!=source_identity(path) or not -60<=age<=4500 or value['schema_version']!=1
                or value['scope']!='native_collection_library' or value['rate_basis']!='observed_storage'
                or value['data_status'] not in ('complete','partial') or not isinstance(value['counts'],dict)
                or not value['counts'] or len(value['counts'])>2*len(SPECS)
                or any(name not in {key+'_'+suffix for key in SPECS for suffix in ('total','24h')}
                       or type(number) is not int or number<0 for name,number in value['counts'].items())):
            return None
        return value
    except (OSError,ValueError,KeyError,TypeError):return None


def save_cache(path,value):
    if value['data_status'] not in ('complete','partial') or not value['counts']:return
    file=cache_path();file.parent.mkdir(parents=True,exist_ok=True)
    temporary=file.with_suffix('.json.tmp')
    temporary.write_text(json.dumps({'source':source_identity(path),'data':value}),encoding='utf-8')
    os.replace(temporary,file)


def summary(path=None):
    global _cache
    # A dashboard read never starts or waits for a library-wide scan.
    with _lock:
        if _cache is None and path is not None:_cache=read_cache(path)
        return dict(_cache) if _cache is not None else unavailable()


class Worker:
    def __init__(self):
        self.task=None;self.stopping=threading.Event();self.wake=asyncio.Event()

    def start(self):self.task=asyncio.create_task(self.run())

    async def stop(self):
        self.stopping.set();self.wake.set()
        if self.task:await self.task

    async def run(self):
        global _cache
        from services.dashboard_integration import native_database
        path=native_database();cached=summary(path)
        if cached['data_status']=='complete':
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(cached['generated_at'])).total_seconds()
            delay=max(0,3600-age)
            try:await asyncio.wait_for(self.wake.wait(),timeout=delay)
            except asyncio.TimeoutError:pass
        while not self.stopping.is_set():
            try:value=await asyncio.to_thread(measure,path,None,self.stopping)
            except Exception:value=unavailable()
            if self.stopping.is_set():return
            with _lock:_cache=value
            try:await asyncio.to_thread(save_cache,path,value)
            except OSError:pass  # A memory result remains usable; no raw store is changed.
            try:await asyncio.wait_for(self.wake.wait(),timeout=3600 if value['data_status']=='complete' else 300)
            except asyncio.TimeoutError:pass


def configured_worker():
    return Worker() if os.environ.get('APP_DASHBOARD_REPORTING_ENABLED')=='1' else None
