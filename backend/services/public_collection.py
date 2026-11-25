"""Read-only, hourly aggregate of the canonical native library, never raw rows."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import threading
import time
import asyncio
import os
import sqlite3

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
                row=con.execute('SELECT '+','.join(expressions)+' FROM '+table,parameters).fetchone()
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


def summary(_path=None):
    # A dashboard read never starts or waits for a library-wide scan.
    with _lock:return dict(_cache) if _cache is not None else unavailable()


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
        while not self.stopping.is_set():
            try:value=await asyncio.to_thread(measure,native_database(),None,self.stopping)
            except Exception:value=unavailable()
            if self.stopping.is_set():return
            with _lock:_cache=value
            try:await asyncio.wait_for(self.wake.wait(),timeout=3600 if value['data_status']=='complete' else 300)
            except asyncio.TimeoutError:pass


def configured_worker():
    return Worker() if os.environ.get('APP_DASHBOARD_REPORTING_ENABLED')=='1' else None
