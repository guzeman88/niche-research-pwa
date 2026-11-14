from contextlib import closing
from urllib.parse import parse_qs,urlparse
from concurrent.futures import ThreadPoolExecutor
import json
import httpx
import pytest
from services.seller_connection import SellerConnection,ConnectionFailure
from services.seller_orders import OrderCapture,normalize_receipt


@pytest.fixture
def connected_inputs(tmp_path):
    clock=[2000000000];calls=[];settings={'shop':'ExampleShop','rows':[],'refresh_error':False}
    def handler(request):
        calls.append((request.method,request.url.path))
        if request.url.path.endswith('/oauth/token'):
            if settings['refresh_error']:return httpx.Response(401,json={'error':'PRIVATE_PROVIDER_TEXT'})
            return httpx.Response(200,json={'access_token':'123.PRIVATE_ACCESS','refresh_token':'123.PRIVATE_REFRESH','expires_in':3600,'scope':'listings_r listings_w shops_r transactions_r'})
        if request.url.path.endswith('/users/me'):return httpx.Response(200,json={'user_id':123})
        if request.url.path.endswith('/users/123/shops'):return httpx.Response(200,json={'shop_id':456,'user_id':123,'shop_name':settings['shop']})
        if request.url.path.endswith('/receipts'):return httpx.Response(200,json={'count':len(settings['rows']),'results':settings['rows']})
        raise AssertionError('Unexpected provider call')
    factory=lambda **kwargs:httpx.Client(transport=httpx.MockTransport(handler),**kwargs)
    store=SellerConnection(tmp_path,'k'*64,'test-key','test-secret','ExampleShop','https://etgen.xyz/api/account/etsy/callback',client_factory=factory,clock=lambda:clock[0])
    return store,clock,calls,settings


def grant(store,account='account-a'):
    start=store.start(account);state=parse_qs(urlparse(start['authorize_url']).query)['state'][0]
    return start,state


def test_pkce_account_binding_replay_and_encrypted_storage(connected_inputs):
    store,clock,calls,settings=connected_inputs;start,state=grant(store)
    query=parse_qs(urlparse(start['authorize_url']).query)
    assert query['code_challenge_method']==['S256'] and len(query['code_challenge'][0])==43
    with pytest.raises(ConnectionFailure):store.complete('account-b',state,'code')
    assert calls==[]
    result=store.complete('account-a',state,'code')
    assert result['connected'] and result['shop_name']=='ExampleShop'
    with pytest.raises(ConnectionFailure):store.complete('account-a',state,'code')
    assert sum(path.endswith('/oauth/token') for _,path in calls)==1
    raw=store.path.read_bytes()
    assert b'PRIVATE_ACCESS' not in raw and b'PRIVATE_REFRESH' not in raw
    assert 'access_token' not in json.dumps(result) and 'refresh_token' not in json.dumps(result)


def test_expired_state_and_wrong_shop_do_not_activate(connected_inputs):
    store,clock,calls,settings=connected_inputs;_,state=grant(store);clock[0]+=601
    with pytest.raises(ConnectionFailure):store.complete('account-a',state,'code')
    assert calls==[]
    _,state=grant(store);settings['shop']='OtherShop'
    with pytest.raises(ConnectionFailure):store.complete('account-a',state,'code')
    assert not store.status('account-a')['connected']


def test_refresh_has_one_owner_and_failure_needs_reconnection(connected_inputs):
    store,clock,calls,settings=connected_inputs;_,state=grant(store);store.complete('account-a',state,'code');clock[0]+=3601
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:store.credentials('account-a'),range(2)))
    assert all(result['shop_id']=='456' for result in results)
    assert sum(path.endswith('/oauth/token') for _,path in calls)==2
    clock[0]+=3601;settings['refresh_error']=True
    with pytest.raises(ConnectionFailure) as error:store.credentials('account-a')
    assert 'PRIVATE_PROVIDER_TEXT' not in str(error.value)
    assert store.status('account-a')['status']=='reconnect_required'


def test_empty_orders_are_unknown_until_success_and_buyer_data_is_not_saved(connected_inputs):
    store,clock,calls,settings=connected_inputs;_,state=grant(store);store.complete('account-a',state,'code');capture=OrderCapture(store)
    assert capture.summary('account-a')['receipts'] is None
    assert capture.sync('account-a')['gross_paid_units']==0
    settings['rows']=[{'receipt_id':77,'is_paid':True,'buyer_email':'PRIVATE_BUYER@example.invalid','formatted_address':'PRIVATE_ADDRESS',
                       'transactions':[{'transaction_id':88,'listing_id':99,'quantity':2}],'refunds':[]}]
    result=capture.sync('account-a');assert result['paid_receipts']==1 and result['gross_paid_units']==2
    assert result['support_minutes_per_order'] is None
    key=result['sample_orders'][0]['order_key'];assert capture.support('account-a',key,0)['support_minutes_per_order']==0
    capture.sync('account-a')
    with closing(store.connect()) as c:assert c.execute('SELECT count(*) FROM seller_order_versions').fetchone()[0]==1
    raw=store.path.read_bytes();assert b'PRIVATE_BUYER' not in raw and b'PRIVATE_ADDRESS' not in raw


def test_missing_paid_order_items_do_not_become_zero_units(connected_inputs):
    store,clock,calls,settings=connected_inputs;_,state=grant(store);store.complete('account-a',state,'code')
    settings['rows']=[{'receipt_id':77,'is_paid':True}]
    assert OrderCapture(store).sync('account-a')['gross_paid_units'] is None
    value=normalize_receipt({'receipt_id':3,'is_paid':None,'transactions':[]})
    assert value['is_paid'] is None and value['actual_platform_fees'] is None and value['profit'] is None
