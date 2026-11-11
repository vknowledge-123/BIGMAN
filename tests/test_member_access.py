"""Real password/TOTP/session/role boundaries; no external broker calls."""
from types import SimpleNamespace
import time

from fastapi.testclient import TestClient
import pyotp
import pytest

from app import access, main
from app.accounts import Accounts, AccountError, DisplaySettings, digest
from app.member_view import filtered, PublishedDashboard

pytestmark = pytest.mark.real_auth
PASSWORD = 'test password long enough!'
PUBLIC = {'X-Requested-With': 'scanner'}


@pytest.fixture
def auth(tmp_path, monkeypatch):
    accounts = Accounts(tmp_path / 'auth.sqlite3')
    monkeypatch.setattr(access, 'accounts', accounts)
    monkeypatch.delenv('SCANNER_PUBLIC_ORIGIN', raising=False)
    monkeypatch.setattr(main, 'published', PublishedDashboard())
    # Any endpoint that accidentally reaches trading must fail the test.
    class Engine:
        calls = 0
        def snapshot(self):
            self.calls += 1
            return dict(stocks=[stock('GREEN')], connected=True, running=True,
                        updated_at='2026-11-11T09:16:02+05:30', access_token='NEVER-PUBLISH')
        @property
        def algo(self):
            raise AssertionError('Member requests must never touch the execution engine')
    engine = Engine()
    monkeypatch.setattr(main, 'scanner', engine)
    client = TestClient(main.app, base_url='http://localhost')
    yield SimpleNamespace(accounts=accounts, client=client, engine=engine)
    client.close()


def stock(symbol, **values):
    result = dict(symbol=symbol, name=symbol, confirmation_status='confirmed',
                  possible_candidate=True, redwala_gira=False, ltp=200,
                  first_candle_turnover=50_000_000, today_opening_volume=250001,
                  circuit_band_eligible=True, circuit_band_status='verified', circuit_band_percent=20,
                  first_candle_open=199, first_candle_close=201, first_candle_color='green',
                  volume_multiplier=4, opening_volume_average=62500,
                  daily_filter={'previous_close':198, 'multiplier':2, 'percent_change':1},
                  error='SENSITIVE BROKER ERROR', security_id='PRIVATE', algo={'secret':'PRIVATE'})
    result.update(values)
    return result


def enroll(auth, admin=False, email='person@example.com'):
    if admin:
        auth.accounts.create(email, PASSWORD, 'Admin', admin=True)
        result = auth.client.post('/api/auth/login', json=dict(email=email,password=PASSWORD),headers=PUBLIC)
    else:
        result = auth.client.post('/api/auth/signup', json=dict(email=email,password=PASSWORD,name='Member'),headers=PUBLIC)
    assert result.status_code == 200, result.text
    challenge = result.json()
    assert challenge['enrollment'] and challenge['qr'].startswith('data:image/svg+xml;base64,')
    response = auth.client.post('/api/auth/verify',headers=PUBLIC,
        json=dict(challenge=challenge['challenge'],code=pyotp.TOTP(challenge['secret']).now()))
    assert response.status_code == 200, response.text
    return response.json()['user'], challenge, response


def test_signup_mfa_approval_dashboard_and_suspension(auth):
    assert auth.client.get('/',follow_redirects=False).headers['location'] == '/login'
    assert auth.client.get('/api/member/state').status_code == 401
    user, challenge, response = enroll(auth)
    assert user['role']=='member' and user['status']=='pending'
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'samesite=strict' in response.headers['set-cookie'].lower()
    assert auth.client.get('/api/member/state').status_code == 403
    assert 'memberDashboard' in auth.client.get('/').text
    auth.accounts.status(user['id'],'active','test-admin')
    data = auth.client.get('/api/member/state').json()
    assert [r['symbol'] for r in data['stocks']] == ['GREEN']
    assert not any(s in str(data) for s in ['PRIVATE','NEVER-PUBLISH','SENSITIVE','security_id','algo','access_token'])
    auth.client.get('/api/member/state')
    assert auth.engine.calls == 1  # Viewer fan-out does not multiply snapshot/broker work.
    auth.accounts.status(user['id'],'suspended','test-admin')
    assert auth.client.get('/api/member/state').status_code == 401


def test_all_admin_endpoints_deny_member_and_anonymous(auth):
    routes = [(path,method.upper()) for path,methods in main.app.openapi()['paths'].items()
              if path.startswith('/api/') and not path.startswith(('/api/auth/','/api/member/'))
              for method in methods if method in ('get','post','put','patch','delete')]
    assert len(routes) >= 20
    for route,method in routes:
        path=route.replace('{uid}','test').replace('{session_id}','test')
        options={'json':{}} if method=='POST' else {}
        assert auth.client.request(method,path,**options).status_code == 401, path
    user, _, _ = enroll(auth)
    auth.accounts.status(user['id'],'active','test-admin')
    for route,method in routes:
        path=route.replace('{uid}','test').replace('{session_id}','test')
        options={'json':{}} if method=='POST' else {}
        assert auth.client.request(method,path,**options,headers={'X-CSRF-Token':user['csrf']}).status_code == 403, path


def test_admin_csrf_settings_and_member_status(auth):
    user, _, _ = enroll(auth,True)
    assert auth.client.get('/api/admin/users').status_code == 200
    settings = DisplaySettings(volume_enabled=True,volume_min=123456).model_dump()
    assert auth.client.post('/api/display-settings',json=settings).status_code == 403
    headers={'X-CSRF-Token':user['csrf']}
    assert auth.client.post('/api/display-settings',json=settings,headers={**headers,'Origin':'https://evil.test'}).status_code == 403
    saved=auth.client.post('/api/display-settings',json=settings,headers=headers)
    assert saved.status_code == 200 and saved.json()['settings']==settings
    assert Accounts(auth.accounts.path).display()['settings']==settings
    # Admin cannot create/promote another admin through the browser.
    assert auth.client.post('/api/admin/users/'+user['id'],json={'status':'active'},headers=headers).status_code == 400
    assert auth.client.post('/api/auth/signup',headers=PUBLIC,json=dict(email='evil@example.com',password=PASSWORD,name='E',role='admin')).status_code == 422
    assert auth.client.post('/api/auth/logout',headers=headers).status_code == 200
    assert auth.client.get('/api/admin/users').status_code == 401


def test_totp_replay_attempt_limits_encryption_and_reset(auth):
    user, challenge, _ = enroll(auth)
    with auth.accounts.db() as db:
        row=db.execute('SELECT * FROM users').fetchone()
        assert row['password'].startswith('$argon2id$') and row['secret'] != challenge['secret']
        assert PASSWORD not in str(dict(row))
        assert db.execute('SELECT token FROM sessions').fetchone()[0] == digest(auth.client.cookies[access.COOKIE])
    login=auth.accounts.password_login(user['email'],PASSWORD)
    assert not login['enrollment'] and 'secret' not in login and 'qr' not in login
    used_code=pyotp.TOTP(challenge['secret']).at(row['last_counter']*30)
    for _ in range(5):
        with pytest.raises(AccountError,match='Invalid or already-used'):
            auth.accounts.verify(login['challenge'],used_code)
    with pytest.raises(AccountError,match='expired'):
        auth.accounts.verify(login['challenge'],used_code)
    auth.accounts.reset(user['email'],mfa=True)
    assert auth.client.get('/api/auth/me').status_code == 401
    assert auth.accounts.password_login(user['email'],PASSWORD)['enrollment']


def test_expiration_and_lost_key_fail_closed(auth):
    user, _, _ = enroll(auth)
    with auth.accounts.db() as db:
        db.execute('UPDATE sessions SET seen=?',(time.time()-1801,))
    assert auth.client.get('/api/auth/me').status_code == 401
    challenge=auth.accounts.password_login(user['email'],PASSWORD)
    with auth.accounts.db() as db:
        db.execute('UPDATE challenges SET expires=0')
    with pytest.raises(AccountError,match='expired'):
        auth.accounts.verify(challenge['challenge'],'123456')
    auth.accounts.path.with_suffix('.key').unlink()
    with pytest.raises(AccountError,match='key is missing'):
        auth.accounts.password_login(user['email'],PASSWORD)


def test_rate_limit_and_transport(auth, monkeypatch):
    for _ in range(3): auth.accounts.throttle('unit',3)
    with pytest.raises(AccountError) as error: auth.accounts.throttle('unit',3)
    assert error.value.status==429
    assert auth.client.post('/api/auth/login',json=dict(email='bad@example.com',password=PASSWORD)).status_code == 403
    assert TestClient(main.app,base_url='http://public.example.com').get('/login').status_code == 400
    monkeypatch.setenv('SCANNER_PUBLIC_ORIGIN','https://scanner.example.com')
    assert auth.client.get('/login').status_code == 400
    auth.client=TestClient(main.app,base_url='https://scanner.example.com')
    _,_,response=enroll(auth,True)
    assert 'secure' in response.headers['set-cookie'].lower()
    assert response.headers['strict-transport-security']=='max-age=31536000'
    assert 'frame-ancestors' in response.headers['content-security-policy']
    for path in ('/static/index.html','/static//index.html','/static/member.html'):
        assert auth.client.get(path).status_code==404


def test_shared_filters_and_exact_priority():
    settings=DisplaySettings().model_dump()
    rows=[stock('BIG',first_candle_turnover=900_000_000),stock('RED',possible_candidate=False,redwala_gira=True,
            first_candle_low_break=True,previous_day_low_cross=True),
          stock('FULL',resistance_break=True,resistance_break_open=True,first_candle_high_break=True),
          stock('UNKNOWN',circuit_band_status='unknown'),stock('TEN',circuit_band_percent=10),
          stock('WAITING',confirmation_status='pending'),stock('RETEST',possible_candidate=False,retest_break=True)]
    assert [r['symbol'] for r in filtered(rows,settings)]==['FULL','RED','BIG']
    settings.update(volume_enabled=True,volume_min=250001)
    assert filtered(rows,settings)==[]
    settings.update(volume_min=250000,price_enabled=True,price_max=200)
    assert len(filtered(rows,settings))==3
    settings['price_max']=199.99
    assert not filtered(rows,settings)
    settings.update(price_enabled=False,setup='redwala')
    assert [r['symbol'] for r in filtered(rows,settings)]==['RED']
