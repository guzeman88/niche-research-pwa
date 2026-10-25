"""Quota fairness and real adapter/cache/estimator behavior; no external calls."""
from contextlib import closing
from datetime import timedelta
import json
import sqlite3

import httpx
import pytest

from models.selling_products import Listing,Packet
from services import selling_collection as cache, selling_discovery as discovery
from services import selling_discovery_sources as sources, feed_request_budget as budget
from services.sales_intelligence import estimator,store


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('VALIDATION_DB_PATH',str(tmp_path/'ledger.sqlite'))
    monkeypatch.setenv('SALES_INTELLIGENCE_ROOT',str(tmp_path/'archive'))
    monkeypatch.setenv('APP_KEYWORD_FEED_ROOT',str(tmp_path/'native'))
    monkeypatch.setattr(discovery,'approval',lambda:{'scopes':['listing_api','shop_api','listing_reviews']})
    from adapters.research import etsy_open_api
    monkeypatch.setattr(etsy_open_api,'_api_key_header',lambda:'fixture-key-never-persist')
    monkeypatch.setattr(sources.time,'sleep',lambda _:None)
    return tmp_path


def review(identity,stamp,number):
    return {'listing_id':identity,'shop_id':7,'created_timestamp':int(stamp.timestamp()),'rating':5,
            'review':f'Public review {number}','buyer_user_id':'private-buyer-must-not-persist'}


def test_batch_and_shop_window_supply_three_products_in_two_calls(isolated):
    at=store.now()-timedelta(seconds=2); calls=[]
    def respond(request):
        calls.append(str(request.url))
        if request.url.path.endswith('/batch'):
            return httpx.Response(200,headers={'x-limit-per-day':'5000','x-remaining-today':'4999'},json={'count':3,'results':[
                {'listing_id':i,'title':f'Planner {i}','shop_id':7,'state':'active','quantity':5,
                 'listing_type':'download','views':50,'num_favorers':3,'tags':['planner'],
                 'images':[{'url_570xN':'https://i.etsystatic.com/fixture/image.jpg'}],
                 'shop':{'shop_id':7,'shop_name':'Fixture shop','transaction_sold_count':40,'user_id':'private-seller'}} for i in (101,102,103)]})
        assert request.url.path.endswith('/shops/7/reviews')
        return httpx.Response(200,headers={'x-limit-per-day':'5000','x-remaining-today':'4998'},json={'count':3,'results':[review(i,at-timedelta(days=1),i) for i in (101,102,103)]})
    with closing(discovery.connect()) as target,target:
        for i in (101,102,103):
            packet=Packet(listings=[Listing(listing_id=str(i),title=f'Planner {i}',source_ref='Fixture')]).model_dump(mode='json')
            discovery._upsert(target,packet,'planner',at.isoformat())
        rows=target.execute('SELECT * FROM candidates ORDER BY listing_id').fetchall()
    with sqlite3.connect(isolated/'requests.sqlite') as native:
        budget.schema(native)
        client=sources.Client(native,'selling-discovery-fixture',discovery.approval()['scopes'],httpx.Client(transport=httpx.MockTransport(respond)))
        client.prefetch(rows)
        for row in rows:
            packet,status=sources.collect(client,row,True)
            assert status=='api_updated' and packet['listings'][0]['image_url']
        assert client.requests==2 and len(calls)==2
        assert native.execute('SELECT count(*) FROM feed_etsy_requests').fetchone()[0]==2
        client.close()
        again=sources.Client(native,'selling-discovery-next',discovery.approval()['scopes'],httpx.Client(transport=httpx.MockTransport(respond)))
        again.prefetch(rows)
        for row in rows:sources.collect(again,row,True)
        assert again.requests==0 and len(calls)==2
        again.close()
    assert all(estimator.calculate(str(i))['value']==10 for i in (101,102,103))
    with cache.database() as con:
        serialized=''.join(r[0] for r in con.execute('SELECT payload FROM cache UNION ALL SELECT payload FROM review_jobs'))
        assert 'private-buyer' not in serialized and 'private-seller' not in serialized and 'fixture-key-never-persist' not in serialized


def test_pagination_resumes_after_four_pages_without_restarting_window(isolated):
    at=store.now(); calls=[]
    rows=[review(101,at-timedelta(seconds=n+10),n) for n in range(550)]
    class Client:
        def get(self,path,scope,params):
            calls.append(dict(params)); start=params['offset']
            return {'count':len(rows),'results':rows[start:start+100]}
    client=Client(); first=cache.reviews(client,'/shops/7/reviews',at)
    assert first['status']=='pending' and len(first['rows'])==400
    second=cache.reviews(client,'/shops/7/reviews',at+timedelta(minutes=15))
    assert second['status']=='complete' and len(second['rows'])==550
    assert [p['offset'] for p in calls]==[0,100,200,300,400,500]
    assert len({p['max_created'] for p in calls})==1
    cache.reviews(client,'/shops/7/reviews',at+timedelta(hours=1))
    assert len(calls)==6


def test_large_review_counts_split_time_ranges_before_offset_limit(isolated):
    at=store.now(); start=int(at.timestamp())-30*86400
    rows=[review(101,at-timedelta(seconds=i*500+1),i) for i in range(1200)]
    calls=[]
    class Client:
        def get(self,path,scope,params):
            calls.append(params)
            values=[r for r in rows if params['min_created']<=r['created_timestamp']<=params['max_created']]
            return {'count':len(values),'results':values[params['offset']:params['offset']+100]}
    client=Client()
    for turn in range(20):
        result=cache.reviews(client,'/shops/7/reviews',at+timedelta(minutes=15*turn))
        if result['status']!='pending':break
    assert result['status']=='complete' and len(result['rows'])==1200
    assert result['start']==start
    assert max(p['offset'] for p in calls)<=1000
    assert len({r['_event'] for r in result['rows']})==1200


@pytest.mark.parametrize('change', ['duplicate','wrong_shop','wrong_listing','changing_count'])
def test_inconsistent_review_pages_do_not_become_complete(isolated,change):
    at=store.now(); rows=[review(101,at-timedelta(seconds=i+1),i) for i in range(150)]
    class Client:
        def get(self,path,scope,params):
            start=params['offset'];result=[dict(r) for r in rows[start:start+100]]
            if start:
                if change=='duplicate':result[0]=rows[0]
                if change=='wrong_shop':result[0]['shop_id']=8
                if change=='wrong_listing':result[0]['listing_id']=999
            return {'count':151 if start and change=='changing_count' else 150,'results':result}
    path='/listings/101/reviews' if change=='wrong_listing' else '/shops/7/reviews'
    assert cache.reviews(Client(),path,at)['status']=='invalid'


def test_global_quota_and_both_lanes_are_reserved_with_shared_headroom(isolated):
    at=store.now();quota={'limit_per_day':100,'remaining_today':99}
    with sqlite3.connect(isolated/'budget.sqlite') as con:
        budget.schema(con)
        for n in range(40):budget.claim(con,quota,f'keyword-{n}',1,at=at)
        assert budget.allocation(con,'keywords',quota=quota)['remaining']==0
        with pytest.raises(budget.CollectionDeferred,match='lane reserve'):
            budget.claim(con,quota,'keyword-over',1,at=at)
        con.rollback()
        for n in range(40):budget.claim(con,quota,f'selling-discovery-{n}',1,at=at)
        assert con.execute('SELECT count(*) FROM feed_etsy_requests').fetchone()[0]==80
        with pytest.raises(budget.CollectionDeferred,match='request budget'):
            budget.claim(con,quota,'selling-discovery-over',1,at=at)


def test_inactive_listing_keeps_history_but_has_no_current_sales_value(isolated):
    at=store.now()-timedelta(seconds=1)
    packet=Packet(listings=[Listing(listing_id='101',title='Inactive planner',source_ref='Fixture')]).model_dump(mode='json')
    window={'start':(at-timedelta(days=30)).isoformat(),'end':at.isoformat(),'complete':True,
            'observed_reviews':1,'review_times':[(at-timedelta(days=2)).isoformat()]}
    estimator.record_capture(packet,at,window,attributes={'state':'inactive','materials':['paper']})
    value=estimator.calculate('101')
    assert value['status']=='inactive_listing' and value['value'] is None
    assert value['review_scenarios']['30']['review_count']==1
    assert estimator.check_delay('101','api_updated')==168


def test_panel_rotation_preserves_pins_evidence_and_retired_membership(isolated):
    at=store.now()
    with store.database(True) as con:
        for i in range(210):
            con.execute('INSERT INTO estimator_tracking VALUES(?,?,?)',(str(i),(at-timedelta(days=8)).isoformat(),int(i==0)))
            con.execute('INSERT INTO estimator_latest VALUES(?,?,?)',(str(i),at.isoformat(),json.dumps({'value':None})))
    with closing(discovery.connect()) as target:
        estimator.expand_panel(target)
    with store.database() as con:
        assert con.execute("SELECT pinned FROM estimator_tracking WHERE listing_id='0'").fetchone()[0]==1
        assert con.execute('SELECT count(*) FROM estimator_latest').fetchone()[0]==210
    with cache.database() as con:
        assert con.execute('SELECT count(*) FROM retired').fetchone()[0]==20
