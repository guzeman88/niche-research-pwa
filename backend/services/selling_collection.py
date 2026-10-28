"""Public-response cache and resumable, bounded review windows. No new scheduler.

Separate from the history archive: older runtimes can ignore this additive file.
Every network page still passes through the native request ledger and approvals.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

from services import selling_discovery as discovery

UTC = timezone.utc
MAX_PAGES_PER_TURN = 4
MAX_REVIEW_ROWS = 10000


@contextmanager
def database():
    directory = discovery.root()
    directory.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(directory / 'collection.sqlite', timeout=20)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA synchronous=FULL')
        con.executescript('''
          CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,captured_at TEXT NOT NULL,expires_at TEXT NOT NULL,payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS review_jobs(id TEXT PRIMARY KEY,path TEXT NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,
            status TEXT NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS review_jobs_path ON review_jobs(path,end DESC);
          CREATE TABLE IF NOT EXISTS control(key TEXT PRIMARY KEY,payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS retired(listing_id TEXT PRIMARY KEY,retired_at TEXT NOT NULL,payload TEXT NOT NULL);
        ''')
        yield con
        con.commit()
    finally:
        con.close()


def cached(key):
    with database() as con:
        row = con.execute('SELECT payload,captured_at FROM cache WHERE key=? AND expires_at>?', (key,discovery.now().isoformat())).fetchone()
    return ({**json.loads(row['payload']), '_captured_at': row['captured_at']} if row else None)


def save(key, payload, hours=6):
    at = discovery.now()
    with database() as con:
        con.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)', (key,at.isoformat(),(at+timedelta(hours=hours)).isoformat(),json.dumps(payload,allow_nan=False)))


def control(key, default=None, value=None):
    with database() as con:
        if value is not None:
            con.execute('INSERT OR REPLACE INTO control VALUES(?,?)',(key,json.dumps(value,allow_nan=False)))
            return value
        row = con.execute('SELECT payload FROM control WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else default


def public_listing(raw):
    """Only fields needed for research/cache; no user IDs or private payloads."""
    fields = ('listing_id','title','shop_id','taxonomy_id','listing_type','original_creation_timestamp',
              'views','num_favorers','quantity','price','tags','state','materials','is_personalizable',
              'description','updated_timestamp')
    result = {k:raw[k] for k in fields if k in raw}
    if isinstance(result.get('price'),dict):
        result['price']={k:v for k,v in result['price'].items() if k in ('amount','divisor','currency_code')}
    if isinstance(result.get('description'),str):
        result['description'] = result['description'][:10000]
    images = raw.get('images',raw.get('Images'))
    shop = raw.get('shop',raw.get('Shop'))
    if isinstance(images,list):
        result['images'] = [{k:v for k,v in x.items() if k in ('url_570xN','url_fullxfull','rank')} for x in images[:20] if isinstance(x,dict)]
    if isinstance(shop,dict):
        result['shop'] = public_shop(shop)
    return result


def public_shop(raw):
    return {k:raw[k] for k in ('shop_id','shop_name','transaction_sold_count','listing_active_count') if k in raw}


def anchored_catalog(client, shop_id, shop):
    """One small public catalog per normal pass; never request private states.

    An active catalog is only a point-in-time supply snapshot. Even a complete
    response cannot establish that every historical/custom product is observed.
    All calls use Client.get's existing approval, lease and shared quota ledger.
    """
    if not str(shop_id).isdecimal() or not {'listing_api','shop_api'} <= set(client.scopes):
        return None
    count = shop.get('listing_active_count')
    if isinstance(count,bool) or not isinstance(count,int) or not 1 <= count <= 30:
        return None
    key = 'anchored_catalog:' + str(shop_id)
    previous = control(key)
    if previous and discovery.now() - discovery._time(previous['captured_at']) < timedelta(hours=24):
        return previous
    if getattr(client,'anchored_catalog_attempted',False):
        return previous
    pilot = control('anchored_pilot', {'shop_ids':[]})
    if shop_id not in pilot['shop_ids'] and len(pilot['shop_ids']) >= 20:
        return None
    # Reserve the turn before dispatch, including a failed response. No retry
    # loop can consume the rest of the normal forty-request allowance.
    client.anchored_catalog_attempted = True
    data = client.get('/shops/'+str(shop_id)+'/listings/active','listing_api',{'limit':100,'offset':0})
    rows, reported = data.get('results'), data.get('count')
    if (not isinstance(rows,list) or isinstance(reported,bool) or not isinstance(reported,int)
            or not 0 <= reported <= 30 or len(rows) != reported):
        return None
    seen = set()
    for row in rows:
        identity = str(row.get('listing_id','')) if isinstance(row,dict) else ''
        if (not identity.isdecimal() or identity in seen or str(row.get('shop_id')) != str(shop_id)
                or row.get('state','active') != 'active' or not isinstance(row.get('title'),str)):
            return None
        seen.add(identity)
    at = discovery.now().isoformat()
    known = set((previous or {}).get('known_listing_ids',(previous or {}).get('listing_ids',[]))) | seen
    result = {'shop_id':str(shop_id),'captured_at':at,'listing_ids':sorted(seen),'known_listing_ids':sorted(known),
              'active_count':reported,'public_complete':True,'complete_catalog':False,
              'products':[public_listing(row) for row in rows],
              'scope':'public_active_catalog_at_capture_not_historical_or_private'}
    control(key,value=result)
    if str(shop_id) not in pilot['shop_ids']:
        pilot['shop_ids'].append(str(shop_id))
        control('anchored_pilot',value=pilot)
    return result


def _persist(job):
    with database() as con:
        con.execute('INSERT OR REPLACE INTO review_jobs VALUES(?,?,?,?,?,?,?)',
                    (job['id'],job['path'],job['start'],job['end'],job['status'],discovery.now().isoformat(),json.dumps(job,allow_nan=False)))


def reviews(client, path, at):
    memo = getattr(client,'review_windows',None)
    if memo is not None and path in memo:
        return memo[path]
    result = _review_window(client,path,at)
    if memo is not None:
        memo[path] = result
    return result


def _review_window(client, path, at):
    """Resume pages at a fixed cutoff; split busy date ranges before offset limits.

    Complete/invalid results are cached six hours. Pending work resumes on the
    next normal pass, without restarting its window. Identity/content duplicates
    and inconsistent page counts fail closed rather than becoming purchases.
    """
    end = int(at.timestamp())
    with database() as con:
        row = con.execute('''SELECT payload FROM review_jobs WHERE path=? AND
            (end>=? OR (status='pending' AND end>=?)) ORDER BY end DESC LIMIT 1''',
                          (path,end-6*3600,end-7*86400)).fetchone()
    job = json.loads(row[0]) if row else None
    if not job:
        start = end-30*86400
        job = {'id': hashlib.sha256(f'{path}:{start}:{end}'.encode()).hexdigest(), 'path':path,
               'start':start,'end':end,'status':'pending','segments':[[start+1,end,0,None]],'rows':[],
               'pages':0,'total':None,'reason':'pages_pending'}
    if job['status'] != 'pending':
        return job
    # Use a set only in memory; normalized public event hashes persist in rows.
    seen = {r['_event'] for r in job['rows']}
    for _ in range(MAX_PAGES_PER_TURN):
        if not job['segments']:
            job.update(status='complete',reason='complete_paginated_time_window')
            _persist(job)
            break
        start, stop, offset, total = job['segments'][0]
        data = client.get(path,'listing_reviews',{'limit':100,'offset':offset,'min_created':start,'max_created':stop})
        job['pages'] += 1
        rows, reported = data.get('results'),data.get('count')
        valid = isinstance(rows,list) and len(rows)<=100 and isinstance(reported,int) and not isinstance(reported,bool) and reported>=0
        if not valid or (total is not None and reported != total):
            job.update(status='invalid',reason='inconsistent_review_page')
            _persist(job)
            break
        # Split large intervals, rather than exhausting the API offset ceiling.
        # The exploratory parent page is discarded before consuming children.
        if offset == 0 and reported>1000 and start<stop:
            middle = (start+stop)//2
            job['segments'][0:1] = [[middle+1,stop,0,None],[start,middle,0,None]]
            _persist(job)
            continue
        normalized = []
        for raw in rows:
            if not isinstance(raw,dict):
                valid = False; break
            identity = str(raw.get('listing_id',''))
            stamp = raw.get('created_timestamp',raw.get('create_timestamp'))
            rating = raw.get('rating')
            shop = str(raw.get('shop_id',''))
            expected = path.split('/')[2]
            if (not identity.isdecimal() or len(identity)>30 or not 1<=int(identity)
                    or isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not start<=stamp<=stop
                    or isinstance(rating,bool) or not isinstance(rating,int) or not 1<=rating<=5
                    or (path.startswith('/listings/') and identity!=expected)
                    or (path.startswith('/shops/') and shop and shop!=expected)):
                valid = False; break
            text = raw.get('review') or ''
            if not isinstance(text,str) or len(text)>5000:
                valid = False; break
            event = hashlib.sha256(json.dumps([identity,stamp,rating,text,raw.get('transaction_id')],sort_keys=True).encode()).hexdigest()
            if event in seen:
                valid = False; break
            seen.add(event)
            normalized.append({'listing_id':identity,'created_timestamp':stamp,'rating':rating,'review':text,
                               **({'shop_id':shop} if shop else {}),'_event':event})
        if not valid or offset+len(rows)>reported or (not rows and offset<reported):
            job.update(status='invalid',reason='invalid_or_duplicate_review_rows')
            _persist(job)
            break
        job['rows'].extend(normalized)
        if len(job['rows'])>MAX_REVIEW_ROWS:
            job.update(status='invalid',reason='bounded_review_window_limit')
            _persist(job)
            break
        if offset+len(rows)==reported:
            job['segments'].pop(0)
        elif len(rows)<100:
            job.update(status='invalid',reason='incomplete_review_page')
        else:
            job['segments'][0] = [start,stop,offset+len(rows),reported]
        if not job['segments'] and job['status']=='pending':
            job.update(status='complete',reason='complete_paginated_time_window')
        _persist(job)
        if job['status']!='pending':
            break
    return job


def metrics():
    with database() as con:
        jobs = {r[0]:r[1] for r in con.execute('SELECT status,count(*) FROM review_jobs GROUP BY status')}
        retired = con.execute('SELECT count(*) FROM retired').fetchone()[0]
    return {'review_windows':jobs,'retired_panel_memberships':retired,
            'last_source_pass':control('last_pass',{}),'panel_policy':{'target':200,'maximum':600,'new_candidates_per_pass':20}}
