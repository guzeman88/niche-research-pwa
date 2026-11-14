"""Bounded, resumable own-shop receipt capture without buyer details or profit inference."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import httpx
from services.seller_connection import configured_store,API,ConnectionFailure


def money(value):
    if not isinstance(value,dict):return None
    amount,divisor,currency=value.get('amount'),value.get('divisor'),value.get('currency_code')
    if isinstance(amount,bool) or not isinstance(amount,int) or amount<0 or isinstance(divisor,bool) or not isinstance(divisor,int) or divisor<=0:return None
    if not isinstance(currency,str) or len(currency)!=3 or not currency.isalpha():return None
    return {'amount':amount,'divisor':divisor,'currency_code':currency.upper()}


def numeric_id(value):
    if isinstance(value,bool):return None
    value=str(value)
    return value if value.isdigit() and 0<int(value)<10**24 else None


def normalize_receipt(raw):
    if not isinstance(raw,dict):raise ValueError('An own-shop receipt must be an object')
    identity=numeric_id(raw.get('receipt_id'))
    if not identity:raise ValueError('A valid own-shop receipt identity is required')
    stamp=lambda x:x if isinstance(x,int) and not isinstance(x,bool) and x>=946684800 else None
    transactions=[]
    for item in raw.get('transactions',[]) if isinstance(raw.get('transactions'),list) else []:
        if not isinstance(item,dict):raise ValueError('A receipt item must be an object')
        quantity=item.get('quantity')
        transactions.append({'transaction_id':numeric_id(item.get('transaction_id')),
            'listing_id':numeric_id(item.get('listing_id')),'quantity':quantity if type(quantity) is int and 0<quantity<=1000000 else None,
            'price':money(item.get('price'))})
    if isinstance(raw.get('refunds'),list) and any(not isinstance(item,dict) for item in raw['refunds']):raise ValueError('A receipt refund must be an object')
    refunds=([{'amount':money(item.get('amount'))} for item in raw['refunds']]
             if isinstance(raw.get('refunds'),list) else None)
    return {'receipt_id':identity,'created_at':stamp(raw.get('create_timestamp',raw.get('created_timestamp'))),
            'modified_at':stamp(raw.get('update_timestamp',raw.get('updated_timestamp'))),
            'is_paid':raw.get('is_paid') if type(raw.get('is_paid')) is bool else None,
            'grandtotal':money(raw.get('grandtotal')),'subtotal':money(raw.get('subtotal')),
            'discount_amt':money(raw.get('discount_amt')),'refunds':refunds,'transactions':transactions,
            'transactions_complete':isinstance(raw.get('transactions'),list) and bool(transactions) and all(item['quantity'] is not None and item['listing_id'] for item in transactions),
            'source':'etsy_own_shop_receipts','net_units':None,'actual_platform_fees':None,'profit':None}


class OrderCapture:
    def __init__(self,store):
        self.store=store
        with closing(store.connect()) as c,c:
            c.executescript('''CREATE TABLE IF NOT EXISTS seller_order_versions(
              account TEXT NOT NULL,identity TEXT NOT NULL,digest TEXT NOT NULL,payload TEXT NOT NULL,observed REAL NOT NULL,
              PRIMARY KEY(account,identity,digest));
              CREATE TABLE IF NOT EXISTS seller_orders(account TEXT NOT NULL,identity TEXT NOT NULL,digest TEXT NOT NULL,
              PRIMARY KEY(account,identity));
              CREATE TABLE IF NOT EXISTS seller_order_sync(account TEXT PRIMARY KEY,since REAL NOT NULL,cutoff REAL NOT NULL,
              offset INTEGER NOT NULL,status TEXT NOT NULL,checked REAL);
              CREATE TABLE IF NOT EXISTS seller_support(account TEXT NOT NULL,identity TEXT NOT NULL,minutes REAL NOT NULL,
              updated REAL NOT NULL,PRIMARY KEY(account,identity));''')

    def sync(self,account,max_pages=3):
        from etgen_production.marketplace import lock
        with lock(self.store.root/'own-orders.lock'):
            credentials=self.store.credentials(account);now=int(self.store.clock())
            with closing(self.store.connect()) as c,c:
                row=c.execute('SELECT * FROM seller_order_sync WHERE account=?',(account,)).fetchone()
                if not row:
                    c.execute('INSERT INTO seller_order_sync VALUES(?,?,?,?,?,?)',(account,now-90*86400,now,0,'pending',None))
                elif row['status']=='completed':
                    c.execute("UPDATE seller_order_sync SET since=?,cutoff=?,offset=0,status='pending' WHERE account=?",(max(946684800,row['cutoff']-86400),now,account))
                state=dict(c.execute('SELECT * FROM seller_order_sync WHERE account=?',(account,)).fetchone())
            try:
                with self.store.factory(timeout=25,follow_redirects=False,trust_env=False) as client:
                    for _ in range(min(3,max(1,int(max_pages)))):
                        response=client.get(API+f'/shops/{credentials["shop_id"]}/receipts',
                            params={'min_last_modified':int(state['since']),'max_last_modified':int(state['cutoff']),
                                    'limit':100,'offset':state['offset']},headers=self.store.headers(credentials['access_token']))
                        response.raise_for_status();body=response.json()
                        rows=body.get('results');count=body.get('count')
                        if not isinstance(rows,list) or len(rows)>100 or type(count) is not int or count<0 or (not rows and state['offset']<count):
                            raise ValueError('Own-shop receipt scan returned an incomplete page')
                        normalized=[normalize_receipt(raw) for raw in rows]
                        with closing(self.store.connect()) as c,c:
                            for item in normalized:
                                identity=hashlib.sha256((credentials['shop_id']+':'+item['receipt_id']).encode()).hexdigest()
                                encoded=json.dumps(item,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(encoded.encode()).hexdigest()
                                c.execute('INSERT OR IGNORE INTO seller_order_versions VALUES(?,?,?,?,?)',(account,identity,digest,encoded,now))
                                c.execute('INSERT INTO seller_orders VALUES(?,?,?) ON CONFLICT(account,identity) DO UPDATE SET digest=excluded.digest',(account,identity,digest))
                            state['offset']+=len(rows);complete=state['offset']>=count
                            c.execute('UPDATE seller_order_sync SET offset=?,status=?,checked=? WHERE account=?',
                                      (state['offset'],'completed' if complete else 'pending',now,account))
                        if complete:break
            except (httpx.HTTPError,ValueError,KeyError,TypeError):
                with closing(self.store.connect()) as c,c:c.execute("UPDATE seller_order_sync SET status='needs_attention' WHERE account=?",(account,))
                raise ConnectionFailure('Own-shop orders could not be completely refreshed. Saved pages are retained; retry after the provider recovers.') from None
            return self.summary(account)

    def support(self,account,identity,minutes):
        if isinstance(minutes,bool) or not isinstance(minutes,(int,float)) or not 0<=minutes<=1440:raise ValueError('Enter observed support minutes, including zero only when known')
        with closing(self.store.connect()) as c,c:
            if not c.execute('SELECT 1 FROM seller_orders WHERE account=? AND identity=?',(account,identity)).fetchone():raise ValueError('Select a captured order first')
            c.execute('INSERT INTO seller_support VALUES(?,?,?,?) ON CONFLICT(account,identity) DO UPDATE SET minutes=excluded.minutes,updated=excluded.updated',
                      (account,identity,minutes,self.store.clock()))
        return self.summary(account)

    def summary(self,account):
        with closing(self.store.connect()) as c:
            state=c.execute('SELECT status,checked FROM seller_order_sync WHERE account=?',(account,)).fetchone()
            rows=c.execute('SELECT o.identity,v.payload,s.minutes FROM seller_orders o JOIN seller_order_versions v ON v.account=o.account AND v.identity=o.identity AND v.digest=o.digest LEFT JOIN seller_support s ON s.account=o.account AND s.identity=o.identity WHERE o.account=?',(account,)).fetchall()
        known=bool(state and state['checked'] is not None)
        paid=[row for row in rows if json.loads(row['payload'])['is_paid'] is True]
        transactions=[item for row in paid for item in json.loads(row['payload'])['transactions']]
        complete=bool(state and state['status']=='completed')
        payment_known=all(json.loads(row['payload'])['is_paid'] is not None for row in rows)
        units=(sum(item['quantity'] for item in transactions) if complete and payment_known and all(json.loads(row['payload'])['transactions_complete'] for row in paid) else None)
        support=(sum(row['minutes'] for row in paid)/len(paid) if paid and complete and all(row['minutes'] is not None for row in paid) else None)
        return {'status':state['status'] if state else 'not_started','receipts':len(rows) if known else None,
                'paid_receipts':len(paid) if known and payment_known else None,'gross_paid_units':units,'support_minutes_per_order':support,
                'checked_at':state['checked'] if state else None,'sample_orders':[{'order_key':row['identity'],'support_minutes':row['minutes']} for row in paid[:20]],
                'net_units':None,'actual_profit':None,'sales_accuracy':None,'qualification_credit':False,
                'notes':['Own-shop receipt scan, not competitor sales. Initial scan covers the last90 days of modifications.',
                         'Refunds and historical revisions are retained; refunded unit allocation and actual platform charges remain unknown.',
                         'Buyer names, addresses, emails and messages are not retained. Support time requires actual logging.',
                         'No estimator accuracy or profitability is established by capture.']}


def sync_active():
    """Called by the existing backend collection cadence; no external timer."""
    root=Path(os.getenv('APP_KEYWORD_FEED_ROOT') or Path.home()/'EtGen/keyword-feed')
    if (root/'state.sqlite').is_file():
        with closing(sqlite3.connect(root/'state.sqlite',timeout=10)) as c:
            if c.execute("SELECT 1 FROM control WHERE name='paused'").fetchone():return {'status':'paused'}
    try:store=configured_store()
    except ConnectionFailure:return {'status':'not_configured'}
    with closing(store.connect()) as c:rows=c.execute("SELECT account FROM seller_connections WHERE status='connected'").fetchall()
    if not rows:return {'status':'not_connected'}
    if len(rows)!=1:return {'status':'operator_review_required'}
    try:return OrderCapture(store).sync(rows[0]['account'])
    except (ConnectionFailure,ValueError):return {'status':'needs_attention'}
