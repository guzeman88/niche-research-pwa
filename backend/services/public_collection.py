"""Read-only, hourly aggregate of the canonical native library, never raw rows."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import threading
import time

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
_checked=0


def measure(path, at=None):
    from services.dashboard_integration import connection
    at=at or datetime.now(timezone.utc)
    since=(at-timedelta(days=1)).isoformat()
    counts={};failed=[];sources={}
    with closing(connection(path)) as con:
        con.execute('BEGIN')
        for table,column in sorted({(t,c) for t,_,c in SPECS.values()}):
            try:
                groups={row['source']:dict(row) for row in con.execute(
                    f'SELECT source,count(*) total,sum(julianday({column})>=julianday(?) AND julianday({column})<=julianday(?)) recent,max({column}) latest FROM {table} GROUP BY source', (since,at.isoformat()))}
                for name,(source_table,providers,_) in SPECS.items():
                    if source_table!=table:continue
                    providers=providers if isinstance(providers,tuple) else (providers,)
                    counts[name+'_total']=sum(groups.get(p,{}).get('total',0) for p in providers)
                    counts[name+'_24h']=sum(groups.get(p,{}).get('recent',0) or 0 for p in providers)
                    for provider in providers:
                        latest=groups.get(provider,{}).get('latest')
                        if latest:sources[provider]=max(sources.get(provider,''),latest)
            except Exception:
                failed.append(table)
    return {'schema_version':1,'scope':'native_collection_library','generated_at':at.isoformat(),
            'window_start':since,'window_hours':24,'counts':counts,'latest':sources,
            'data_status':'partial' if failed else 'complete','rate_basis':'observed_storage'}


def summary(path):
    global _cache,_checked
    with _lock:
        if _cache is not None and time.monotonic()-_checked<3600:return _cache
        try:value=measure(path)
        except Exception:
            value={'schema_version':1,'scope':'native_collection_library','generated_at':datetime.now(timezone.utc).isoformat(),
                   'window_hours':24,'counts':{},'latest':{},'data_status':'unavailable','rate_basis':'observed_storage'}
        _cache=value;_checked=time.monotonic()
        return value
