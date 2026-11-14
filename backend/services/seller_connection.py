"""Account-bound Etsy OAuth with encrypted local credentials and refresh leases."""
from __future__ import annotations

import base64
from contextlib import closing,contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlparse

from cryptography.fernet import Fernet, InvalidToken
import httpx

SCOPES = ('listings_r','listings_w','shops_r','transactions_r')
TOKEN_URL = 'https://api.etsy.com/v3/public/oauth/token'
API = 'https://openapi.etsy.com/v3/application'


class ConnectionFailure(ValueError):
    """Messages are controlled labels, never provider bodies or credentials."""


@contextmanager
def refresh_lease(path):
    from etgen_production.marketplace import lock
    deadline=time.monotonic()+30
    while True:
        manager=lock(path)
        try:manager.__enter__();break
        except ValueError:
            if time.monotonic()>=deadline:raise ConnectionFailure('Another seller credential refresh is still running; retry shortly') from None
            time.sleep(.05)
    try:yield
    finally:manager.__exit__(None,None,None)


class SellerConnection:
    def __init__(self, root, secret, keystring, shared_secret, expected_shop,
                 redirect_uri, *, client_factory=httpx.Client, clock=time.time):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'seller-connection.sqlite';self.clock=clock;self.factory=client_factory
        if not isinstance(secret,str) or len(secret)<40:raise ConnectionFailure('The private credential encryption key is unavailable')
        if not keystring or not shared_secret:raise ConnectionFailure('The Etsy application key is unavailable')
        if not re.fullmatch(r'[A-Za-z0-9]{4,40}',expected_shop or ''):raise ConnectionFailure('Configure the verified expected seller shop first')
        uri=urlparse(redirect_uri)
        if uri.scheme!='https' or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment or uri.path!='/api/account/etsy/callback':
            raise ConnectionFailure('Configure the exact HTTPS Etsy account callback')
        if uri.hostname not in ('etgen.xyz','etgen.netlify.app'):raise ConnectionFailure('The seller callback must use an approved EtGen account origin')
        self.redirect=redirect_uri;self.expected_shop=expected_shop;self.keystring=keystring;self.shared_secret=shared_secret
        key=base64.urlsafe_b64encode(hashlib.sha256(b'etgen-etsy-credentials-v1\0'+secret.encode()).digest())
        self.cipher=Fernet(key)
        with closing(self.connect()) as c,c:
            c.executescript('''CREATE TABLE IF NOT EXISTS oauth_flows(
                identity TEXT PRIMARY KEY,account TEXT NOT NULL,created REAL NOT NULL,status TEXT NOT NULL,secret BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS seller_connections(
                account TEXT PRIMARY KEY,shop_id TEXT NOT NULL,shop_name TEXT NOT NULL,secret BLOB NOT NULL,
                expires REAL NOT NULL,connected REAL NOT NULL,status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS connection_events(
                id INTEGER PRIMARY KEY,account TEXT NOT NULL,event TEXT NOT NULL,at REAL NOT NULL);''')

    def connect(self):
        c=sqlite3.connect(self.path,timeout=15);c.row_factory=sqlite3.Row
        return c

    def account(self,value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value):raise ConnectionFailure('Sign into an administrator account before connecting Etsy')
        return value

    def seal(self,account,purpose,value):
        return self.cipher.encrypt(json.dumps({'account':account,'purpose':purpose,'value':value},sort_keys=True).encode())

    def unseal(self,account,purpose,value):
        try:
            data=json.loads(self.cipher.decrypt(value))
            if data['account']!=account or data['purpose']!=purpose:raise ValueError()
            return data['value']
        except (InvalidToken,ValueError,KeyError,TypeError):raise ConnectionFailure('Stored Etsy credentials failed verification; reconnect the seller account') from None

    def start(self,account):
        account=self.account(account);state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        with closing(self.connect()) as c,c:
            c.execute("UPDATE oauth_flows SET status='superseded' WHERE account=? AND status='pending'",(account,))
            c.execute('INSERT INTO oauth_flows VALUES(?,?,?,?,?)',
                      (hashlib.sha256(state.encode()).hexdigest(),account,self.clock(),'pending',self.seal(account,'pkce',{'verifier':verifier})))
        query=urlencode(dict(response_type='code',client_id=self.keystring,redirect_uri=self.redirect,
                             scope=' '.join(SCOPES),state=state,code_challenge=challenge,code_challenge_method='S256'))
        return {'authorize_url':'https://www.etsy.com/oauth/connect?'+query,'expected_shop':self.expected_shop,
                'expires_in':600,'scopes':list(SCOPES),'publication_performed':False}

    def _tokens(self,payload):
        if (not isinstance(payload,dict) or not isinstance(payload.get('access_token'),str) or
            not isinstance(payload.get('refresh_token'),str) or not payload['access_token'] or not payload['refresh_token']):
            raise ConnectionFailure('Etsy did not return complete credentials; reconnect')
        expires=payload.get('expires_in')
        if isinstance(expires,bool) or not isinstance(expires,(int,float)) or not 0<expires<=86400:
            raise ConnectionFailure('Etsy returned an invalid credential expiry')
        if payload.get('scope') and not set(SCOPES)<=set(str(payload['scope']).split()):
            raise ConnectionFailure('The Etsy connection is missing required seller permissions')
        return {k:payload[k] for k in ('access_token','refresh_token','expires_in')}

    def headers(self,token):
        return {'Authorization':'Bearer '+token,'x-api-key':self.keystring+':'+self.shared_secret}

    def complete(self,account,state,code):
        account=self.account(account)
        if not isinstance(state,str) or not 20<=len(state)<=200 or not isinstance(code,str) or not 1<=len(code)<=2000:
            raise ConnectionFailure('Restart the Etsy connection; its callback is incomplete')
        identity=hashlib.sha256(state.encode()).hexdigest()
        with closing(self.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM oauth_flows WHERE identity=? AND account=?',(identity,account)).fetchone()
            if not row or row['status']!='pending' or not 0<=self.clock()-row['created']<=600:
                raise ConnectionFailure('The Etsy connection expired or was already used; restart it')
            secret=self.unseal(account,'pkce',row['secret'])
            c.execute("UPDATE oauth_flows SET status='exchanging' WHERE identity=?",(identity,))
        try:
            with self.factory(timeout=25,follow_redirects=False,trust_env=False) as client:
                response=client.post(TOKEN_URL,data={'grant_type':'authorization_code','client_id':self.keystring,
                                     'redirect_uri':self.redirect,'code':code,'code_verifier':secret['verifier']})
                response.raise_for_status();tokens=self._tokens(response.json());headers=self.headers(tokens['access_token'])
                response=client.get(API+'/users/me',headers=headers);response.raise_for_status();user=response.json()
                user_id=str(user.get('user_id',''))
                if not user_id.isdigit() or int(user_id)<=0:raise ConnectionFailure('Etsy did not verify the seller identity')
                response=client.get(API+f'/users/{user_id}/shops',headers=headers);response.raise_for_status();body=response.json()
                shops=body.get('results',[body]);shop=next((s for s in shops if str(s.get('shop_name','')).casefold()==self.expected_shop.casefold() and str(s.get('user_id',''))==user_id),None)
                if not shop or not str(shop.get('shop_id','')).isdigit():raise ConnectionFailure('The signed-in Etsy seller does not own the expected shop')
                # Read verification only. No listing is created to test a scope.
                response=client.get(API+f'/shops/{shop["shop_id"]}/receipts',params={'limit':1},headers=headers)
                response.raise_for_status()
            with closing(self.connect()) as c,c:
                c.execute('INSERT INTO seller_connections VALUES(?,?,?,?,?,?,?) ON CONFLICT(account) DO UPDATE SET shop_id=excluded.shop_id,shop_name=excluded.shop_name,secret=excluded.secret,expires=excluded.expires,connected=excluded.connected,status=excluded.status',
                          (account,str(shop['shop_id']),shop['shop_name'],self.seal(account,'tokens',tokens),self.clock()+tokens['expires_in'],self.clock(),'connected'))
                c.execute("UPDATE oauth_flows SET status='completed' WHERE identity=?",(identity,))
                c.execute('INSERT INTO connection_events(account,event,at) VALUES(?,?,?)',(account,'seller_connected_read_verified',self.clock()))
        except (httpx.HTTPError,ValueError,KeyError,TypeError):
            with closing(self.connect()) as c,c:c.execute("UPDATE oauth_flows SET status='restart_required' WHERE identity=?",(identity,))
            raise ConnectionFailure('Etsy connection could not be verified. Check the expected seller account and restart the connection.') from None
        return self.status(account)

    def status(self,account):
        account=self.account(account)
        with closing(self.connect()) as c:
            row=c.execute('SELECT shop_name,connected,expires,status FROM seller_connections WHERE account=?',(account,)).fetchone()
            verified=bool(c.execute("SELECT 1 FROM connection_events WHERE account=? AND event='draft_upload_verified' LIMIT 1",(account,)).fetchone())
        return {'configured':True,'expected_shop':self.expected_shop,'connected':bool(row and row['status']=='connected'),
                'shop_name':row['shop_name'] if row else None,'connected_at':row['connected'] if row else None,
                'status':row['status'] if row else 'not_connected','draft_upload_verified':verified,
                'requested_scopes':list(SCOPES),'automatic_publication':False}

    def credentials(self,account):
        account=self.account(account)
        with refresh_lease(self.root/'credential-refresh.lock'):
            with closing(self.connect()) as c:row=c.execute('SELECT * FROM seller_connections WHERE account=?',(account,)).fetchone()
            if not row or row['status']!='connected':raise ConnectionFailure('Connect the expected Etsy seller account first')
            tokens=self.unseal(account,'tokens',row['secret'])
            if row['expires']<=self.clock()+60:
                try:
                    with self.factory(timeout=25,follow_redirects=False,trust_env=False) as client:
                        response=client.post(TOKEN_URL,data={'grant_type':'refresh_token','client_id':self.keystring,'refresh_token':tokens['refresh_token']})
                        response.raise_for_status();tokens=self._tokens(response.json())
                    with closing(self.connect()) as c,c:c.execute('UPDATE seller_connections SET secret=?,expires=? WHERE account=?',
                        (self.seal(account,'tokens',tokens),self.clock()+tokens['expires_in'],account))
                except (httpx.HTTPError,ValueError,KeyError,TypeError):
                    with closing(self.connect()) as c,c:c.execute("UPDATE seller_connections SET status='reconnect_required' WHERE account=?",(account,))
                    raise ConnectionFailure('Etsy credential refresh was not confirmed; reconnect before retrying') from None
            return {'shop_id':row['shop_id'],'access_token':tokens['access_token'],
                    'keystring':self.keystring,'shared_secret':self.shared_secret}


def configured_store():
    from services.production import engine,Engine
    if Engine is None:raise ConnectionFailure('Install the verified production engine before connecting Etsy')
    root=engine().root/'private-seller'
    path=root/'settings.json'
    if not path.is_file():raise ConnectionFailure('The verified seller shop and HTTPS callback need operator setup')
    settings=json.loads(path.read_text())
    return SellerConnection(root,os.getenv('PIPELINE_API_TOKEN',''),os.getenv('ETSY_API_KEYSTRING',''),
        os.getenv('ETSY_SHARED_SECRET',''),settings.get('expected_shop_name'),settings.get('redirect_uri'))


def account_id(request):
    return getattr(request.state,'account_id',None) or 'local-operator'
