"""Bounded public-catalog evidence acquisition; no network or live databases."""
from datetime import timedelta
import json
import sqlite3

import httpx
import pytest

from services import selling_collection as cache, selling_discovery as discovery
from services import selling_discovery_sources as sources, feed_request_budget as budget
from services.sales_intelligence import store


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('VALIDATION_DB_PATH',str(tmp_path/'ledger.sqlite'))
    monkeypatch.setenv('SALES_INTELLIGENCE_ROOT',str(tmp_path/'archive'))
    monkeypatch.setenv('APP_KEYWORD_FEED_ROOT',str(tmp_path/'native'))
    monkeypatch.setattr(discovery,'approval',lambda:{'scopes':['listing_api','shop_api']})
    from adapters.research import etsy_open_api
    monkeypatch.setattr(etsy_open_api,'_api_key_header',lambda:'fixture-no-live-key')
    monkeypatch.setattr(sources.time,'sleep',lambda _:None)
    return tmp_path


def rows():
    return [{'listing_id':n,'shop_id':7,'title':'Fixture '+str(n),'state':'active',
             'views':50,'num_favorers':2,'quantity':5,'user_id':'private-never-retain'} for n in (101,102)]


def test_catalog_one_bounded_page_counts_and_caches_without_implying_complete_history(isolated):
    calls=[]
    def respond(request):
        calls.append(str(request.url))
        assert request.url.path.endswith('/shops/7/listings/active')
        assert dict(request.url.params)=={'limit':'100','offset':'0'}
        return httpx.Response(200,json={'count':2,'results':rows()})
    with sqlite3.connect(isolated/'requests.sqlite') as native:
        budget.schema(native)
        client=sources.Client(native,'selling-discovery-fixture',['listing_api','shop_api'],httpx.Client(transport=httpx.MockTransport(respond)))
        value=cache.anchored_catalog(client,'7',{'listing_active_count':2})
        assert value['listing_ids']==['101','102'] and value['public_complete']
        assert value['complete_catalog'] is False
        assert 'private-never-retain' not in json.dumps(value)
        assert client.requests==1
        assert cache.anchored_catalog(client,'8',{'listing_active_count':2}) is None
        assert cache.anchored_catalog(client,'7',{'listing_active_count':2})==value
        assert len(calls)==1 and native.execute('SELECT count(*) FROM feed_etsy_requests').fetchone()[0]==1
        sources.capture_catalog(value,'Fixture shop')
        with store.database() as con:
            evidence=[json.loads(r[0]) for r in con.execute('SELECT payload FROM estimator_evidence')]
            assert len(evidence)==2
            assert not con.execute('SELECT 1 FROM estimator_tracking').fetchone()
            assert all(x['attributes']['shop_id']=='7' and x['review_window'] is None for x in evidence)
        client.close()


@pytest.mark.parametrize('count',[None,True,0,31,1000])
def test_unknown_large_or_empty_catalog_does_not_dispatch(isolated,count):
    class Client:
        scopes={'listing_api','shop_api'}
        def get(self,*args):raise AssertionError('No request should be dispatched')
    assert cache.anchored_catalog(Client(),'7',{'listing_active_count':count}) is None


@pytest.mark.parametrize('payload',[
    {'count':3,'results':rows()},
    {'count':2,'results':[rows()[0],rows()[0]]},
    {'count':2,'results':[rows()[0],{**rows()[1],'shop_id':8}]},
])
def test_bad_response_does_not_claim_coverage(isolated,payload):
    class Client:
        scopes={'listing_api','shop_api'}
        def get(self,*args):return payload
    assert cache.anchored_catalog(Client(),'7',{'listing_active_count':2}) is None
    assert cache.control('anchored_catalog:7') is None


def test_pilot_bound_and_stale_refresh(isolated,monkeypatch):
    cache.control('anchored_pilot',value={'shop_ids':[str(i) for i in range(1,21)]})
    class Client:
        scopes={'listing_api','shop_api'}
        calls=0
        def get(self,*args):self.calls+=1;return {'count':2,'results':rows()}
    client=Client()
    assert cache.anchored_catalog(client,'21',{'listing_active_count':2}) is None
    first=cache.anchored_catalog(client,'7',{'listing_active_count':2})
    at=discovery.now()+timedelta(hours=25)
    monkeypatch.setattr(discovery,'now',lambda:at)
    assert cache.anchored_catalog(Client(),'7',{'listing_active_count':2})['captured_at']!=first['captured_at']


def test_catalog_path_cannot_request_private_states_or_skip_shop_permission(isolated):
    with sqlite3.connect(isolated/'requests.sqlite') as native:
        budget.schema(native)
        client=sources.Client(native,'fixture',['listing_api'])
        with pytest.raises(ValueError,match='approval'):
            client.get('/shops/7/listings/active','listing_api',{'limit':100,'offset':0})
        with pytest.raises(ValueError,match='Unsupported source path'):
            client.get('/shops/7/listings','listing_api',{'state':'inactive'})
        assert client.requests==0
        client.close()


def test_full_tracking_panel_still_retains_complete_catalog_review_coverage(isolated):
    from services.sales_intelligence import estimator
    at=store.now()-timedelta(seconds=2)
    with store.database(True) as con:
        con.executemany('INSERT INTO estimator_tracking VALUES(?,?,1)',
                        [(str(i),at.isoformat()) for i in range(1000,1600)])
    catalog={'shop_id':'7','captured_at':at.isoformat(),'listing_ids':['101','102'],
             'active_count':2,'products':rows(),'public_complete':True,'complete_catalog':False}
    cache.control('anchored_catalog:7',value=catalog)
    sources.capture_catalog(catalog,'Fixture shop')
    raw=[{'listing_id':101,'shop_id':7,'created_timestamp':int((at-timedelta(hours=2)).timestamp()),
          'rating':5,'review':'Fixture public text'}]
    followed=estimator.follow_reviewed_products(raw,at-timedelta(days=30),at,'7','999',{'shop':'Fixture shop'})
    assert set(followed)=={'101','102'}
    with store.database() as con:
        assert con.execute('SELECT count(*) FROM estimator_tracking').fetchone()[0]==600
        windows={r['listing_id']:json.loads(r['payload'])['review_window'] for r in con.execute(
            "SELECT listing_id,payload FROM estimator_evidence WHERE json_extract(payload,'$.review_window.complete')=1")}
    assert windows['101']['observed_reviews']==1
    assert windows['102']['observed_reviews']==0 and windows['102']['complete'] is True
