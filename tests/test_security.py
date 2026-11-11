"""Adversarial HTTP tests use real middleware/auth and disposable account data."""
import asyncio
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pytest

from app import main, security
from app.accounts import AccountError
from app.algo_strategy import AlgoSettings
from app.schemas import VolumeFilterSettings
from app.storage import ConfigStore
from test_member_access import auth, enroll, PASSWORD, PUBLIC, stock

pytestmark = pytest.mark.real_auth


@pytest.mark.parametrize('path',['/health','/login','/static/app.js','/api/member/state','/openapi.json'])
def test_host_origin_and_public_schema(auth,path):
    assert auth.client.get(path,headers={'Host':'evil.example'}).status_code==400
    assert auth.client.get(path,headers={'Origin':'https://evil.example'}).status_code==403
    assert auth.client.get(path,headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert auth.client.get('/openapi.json').status_code==401
    assert auth.client.get('/docs').status_code==404
    assert auth.client.get('/redoc').status_code==404
    health=auth.client.get('/health')
    assert health.json()=={'info':{'title':'Dhan Turnover Scanner'}}
    assert "object-src 'none'" in health.headers['content-security-policy']


@pytest.mark.parametrize('payload,headers,expected',[
    ('x'*17000,{'content-type':'application/json'},413),
    ('{}',{'content-type':'application/json','content-encoding':'gzip'},415),
    ('a=b',{'content-type':'application/x-www-form-urlencoded'},415),
    ('x',{'content-type':'multipart/form-data; boundary=evil'},415),
    ('['*100+'0'+']'*100,{'content-type':'application/json'},400),
    ('{broken',{'content-type':'application/json'},400),
    ('{}',{'content-type':'application/json','content-length':'-1'},400),
    ('{}',{'content-type':'application/json','content-length':'1'},400),
])
def test_bad_bodies_are_rejected_before_handlers(auth,payload,headers,expected):
    response=auth.client.post('/api/auth/login',content=payload,headers={**PUBLIC,**headers})
    assert response.status_code==expected
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['cache-control']=='no-store'


def test_header_url_method_bounds_and_private_files(auth):
    assert auth.client.get('/health',headers={'x-flood':'X'*17000}).status_code==431
    assert auth.client.get('/health?'+('x'*4100)).status_code==414
    assert auth.client.request('TRACE','/health').status_code==405
    for path in ['/data/auth.key','/data/auth.sqlite3','/.env','/static/%2e%2e/data/auth.key','/static//index.html']:
        assert auth.client.get(path).status_code in (400,404)
    # Upload authentication occurs before a large body is parsed.
    assert auth.client.post('/api/preopen/preview',content='x'*300000,headers={'content-type':'application/json'}).status_code==401


def test_validation_never_echoes_password_or_totp(auth):
    secret='DO-NOT-ECHO-PASSWORD'
    response=auth.client.post('/api/auth/login',headers=PUBLIC,json={'email':'a@example.com','password':{'leak':secret}})
    assert response.status_code==422 and secret not in response.text and 'input' not in response.json()['detail'][0]
    response=auth.client.post('/api/auth/verify',headers=PUBLIC,json={'challenge':'x'*32,'code':'١٢٣٤٥٦'})
    assert response.status_code==422 and '١٢٣٤٥٦' not in response.text


def test_persistent_account_login_limit_and_untrusted_forwarded_ip(auth,monkeypatch):
    # Keep ingress out of this test to isolate the persistent account budget.
    monkeypatch.setattr(security.limits,'take',lambda *args:True)
    for i in range(10):
        response=auth.client.post('/api/auth/login',headers={**PUBLIC,'X-Forwarded-For':f'10.0.0.{i}'},
                                  json={'email':' PERSON@example.com ','password':PASSWORD})
        assert response.status_code==401
    response=auth.client.post('/api/auth/login',headers={**PUBLIC,'X-Forwarded-For':'8.8.8.8'},
                              json={'email':'person@example.com','password':PASSWORD})
    assert response.status_code==429 and response.headers['retry-after']=='900'
    from app.accounts import Accounts
    replacement=Accounts(auth.accounts.path)
    with pytest.raises(AccountError) as error:
        replacement.throttle('login:account:person@example.com',10)
    assert error.value.status==429


def test_request_flood_limit_and_bounded_bucket_memory(auth,monkeypatch):
    monotonic=security.time.monotonic()
    monkeypatch.setattr(security.time,'monotonic',lambda:monotonic)
    for _ in range(120): assert auth.client.get('/health').status_code==200
    assert auth.client.get('/health',headers={'X-Forwarded-For':'8.8.8.8'}).status_code==429
    buckets=security.RequestLimits()
    for i in range(4096): assert buckets.take(str(i),1,1)
    assert not buckets.take('overflow',1,1)
    assert len(buckets.buckets)==4096


def test_password_work_is_bounded_and_otp_budget_survives_new_challenges(auth):
    slots=auth.accounts.password_slots
    assert slots.acquire(False) and slots.acquire(False)
    try:
        with pytest.raises(AccountError) as error:
            auth.accounts.password_login('none@example.com',PASSWORD)
        assert error.value.status==429
    finally:
        slots.release();slots.release()
    uid=auth.accounts.create('otp@example.com',PASSWORD,'OTP')
    for _ in range(2):
        challenge=auth.accounts.challenge(uid)
        for _ in range(5):
            with pytest.raises(AccountError) as error:
                auth.accounts.verify(challenge['challenge'],'abcdef')
            assert error.value.status==401
    challenge=auth.accounts.challenge(uid)
    with pytest.raises(AccountError) as error:
        auth.accounts.verify(challenge['challenge'],'abcdef')
    assert error.value.status==429


def test_sql_injection_is_data_not_a_query(auth):
    name="Robert'); DROP TABLE users; --"
    uid=auth.accounts.create('sql@example.com',PASSWORD,name)
    assert auth.accounts.users()[0]['name']==name
    assert auth.accounts.users()[0]['id']==uid
    response=auth.client.post('/api/auth/login',headers=PUBLIC,json={'email':"' OR 1=1 --",'password':PASSWORD})
    assert response.status_code==400 and not auth.client.cookies
    assert len(auth.accounts.users())==1


def test_streamed_body_size_and_timeout(monkeypatch):
    async def run(mode):
        called=[];sent=[]
        async def downstream(*args):called.append(True)
        guard=security.SecurityMiddleware(downstream)
        scope={'type':'http','http_version':'1.1','scheme':'http','method':'POST','path':'/api/auth/login',
               'raw_path':b'/api/auth/login','query_string':b'', 'server':('localhost',80),
               'client':('127.0.0.1',1234),'headers':[(b'host',b'localhost'),(b'content-type',b'application/json')]}
        async def receive():
            if mode=='timeout':raise asyncio.TimeoutError()
            return {'type':'http.request','body':b'x'*9000,'more_body':True}
        async def send(message):sent.append(message)
        await guard(scope,receive,send)
        assert not called
        return sent[0]['status'],guard.readers
    assert asyncio.run(run('large'))==(413,0)
    assert asyncio.run(run('timeout'))==(408,0)


@pytest.mark.parametrize('admin',[False,True])
def test_stored_script_payloads_render_as_text(auth,monkeypatch,tmp_path,admin):
    pw=pytest.importorskip('playwright.sync_api')
    payload='<img src=x onerror="window.attacked=1">'
    user,_,_=enroll(auth,admin)
    with auth.accounts.db() as db:db.execute('UPDATE users SET name=? WHERE id=?',(payload,user['id']))
    if not admin:auth.accounts.status(user['id'],'active','local-test')
    monkeypatch.setattr(main,'store',ConfigStore(tmp_path/'config.json'))
    monkeypatch.setattr(type(auth.engine),'algo',SimpleNamespace(snapshot=lambda:dict(settings=AlgoSettings().model_dump(),sessions=[])))
    monkeypatch.setattr(auth.engine,'snapshot',lambda:dict(stocks=[stock('SAFE',name=payload,daily_filter=None)],
       running=True,connected=True,status='Connected',unresolved_symbols=[],updated_at='2026-11-11T09:16:02+05:30',
       volume_filters=VolumeFilterSettings().model_dump()))
    def route(r):
        url=urlsplit(r.request.url)
        assert url.hostname=='localhost'
        result=auth.client.request(r.request.method,url.path,content=r.request.post_data,headers=r.request.headers)
        r.fulfill(status=result.status_code,body=result.content,headers=dict(result.headers))
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page();page.route('**/*',route);page.goto('http://localhost/')
            selector='#memberAccounts' if admin else '#memberRows'
            pw.expect(page.locator(selector)).to_contain_text(payload)
            assert page.locator(selector+' img').count()==0
            assert page.evaluate('window.attacked || 0')==0
            assert page.locator('#accountName img').count()==0
        finally:browser.close()
