"""Browser -> production auth/API -> SQLite, with synthetic market snapshots."""
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
import tempfile

from fastapi.testclient import TestClient
import pyotp
import pytest

from app import main
from app.algo_strategy import AlgoSettings
from app.schemas import VolumeFilterSettings
from app.storage import ConfigStore
from test_member_access import auth, PASSWORD, stock

pytestmark = pytest.mark.real_auth


@pytest.mark.parametrize('width',[1440,390])
def test_signup_approval_shared_dashboard_and_suspension(auth,monkeypatch,tmp_path,width):
    pw=pytest.importorskip('playwright.sync_api')
    monkeypatch.setattr(main,'store',ConfigStore(tmp_path/'config.json'))
    monkeypatch.setattr(type(auth.engine),'algo',SimpleNamespace(snapshot=lambda:dict(settings=AlgoSettings().model_dump(),sessions=[])))
    rows=[stock('GREEN',daily_filter=None),stock('RED',possible_candidate=False,redwala_gira=True,
            first_candle_color='red',today_opening_volume=100000,first_candle_turnover=20000000,daily_filter=None)]
    monkeypatch.setattr(auth.engine,'snapshot',lambda:dict(stocks=rows,running=True,connected=True,
        updated_at='2026-11-11T09:16:02+05:30',status='Connected',unresolved_symbols=[],volume_filters=VolumeFilterSettings().model_dump()))
    auth.accounts.create('owner@example.com',PASSWORD,'Owner',admin=True)
    def attach(context):
        client=TestClient(main.app,base_url='http://localhost',follow_redirects=False)
        def route(r):
            url=urlsplit(r.request.url)
            if url.hostname!='localhost':
                r.abort();return
            response=client.request(r.request.method,url.path,content=r.request.post_data,headers=r.request.headers)
            r.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers))
        context.route('**/*',route)
        return client
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        clients=[]
        try:
            member_context=browser.new_context(viewport=dict(width=width,height=1000))
            admin_context=browser.new_context(viewport=dict(width=width,height=1000))
            clients.extend([attach(member_context),attach(admin_context)])
            member=member_context.new_page();admin=admin_context.new_page();errors=[]
            for page in [member,admin]:page.on('pageerror',lambda e:errors.append(str(e)))
            member.goto('http://localhost/signup')
            pw.expect(member.locator('#formTitle')).to_have_text('Create your account')
            member.screenshot(path=str(Path(tempfile.gettempdir())/f'scanner-signup-{width}.png'),full_page=True)
            assert member.evaluate('document.documentElement.scrollWidth <= innerWidth')
            member.locator('#name').fill('Test Member');member.locator('#email').fill('member@example.com')
            member.locator('#password').fill(PASSWORD);member.locator('#confirmPassword').fill(PASSWORD)
            member.locator('#identitySubmit').click()
            pw.expect(member.locator('#otpForm')).to_be_visible()
            secret=member.locator('#setupKey').text_content()
            member.locator('#otp').fill(pyotp.TOTP(secret).now());member.locator('#otpSubmit').click()
            pw.expect(member.locator('#pendingAccess')).to_be_visible()
            assert member.locator('#startButton').count()==0
            admin.goto('http://localhost/login');admin.locator('#email').fill('owner@example.com');admin.locator('#password').fill(PASSWORD)
            admin.locator('#identitySubmit').click();pw.expect(admin.locator('#otpForm')).to_be_visible()
            secret=admin.locator('#setupKey').text_content()
            admin.locator('#otp').fill(pyotp.TOTP(secret).now());admin.locator('#otpSubmit').click()
            approve=admin.get_by_role('button',name='Approve',exact=True)
            pw.expect(approve).to_be_enabled();approve.click()
            pw.expect(member.locator('#memberRows tr')).to_have_count(2,timeout=10000)
            assert member.locator('input,select').count()==0
            assert 'GREEN' in member.locator('#memberRows').inner_text()
            admin.locator('#dashboardVolumeEnabled').check()
            pw.expect(admin.locator('#sharedDisplayStatus')).to_contain_text('Shared settings saved')
            pw.expect(member.locator('#memberRows tr')).to_have_count(1,timeout=10000)
            assert 'RED' not in member.locator('#memberRows').inner_text()
            admin.reload();pw.expect(admin.locator('#dashboardVolumeEnabled')).to_be_checked()
            member.reload();pw.expect(member.locator('#memberRows tr')).to_have_count(1)
            member.screenshot(path=str(Path(tempfile.gettempdir())/f'scanner-member-{width}.png'),full_page=True)
            assert member.evaluate('document.documentElement.scrollWidth <= innerWidth')
            admin.get_by_role('button',name='Suspend',exact=True).click()
            pw.expect(member).to_have_url('http://localhost/login',timeout=10000)
            assert errors==[]
        finally:
            browser.close()
            for client in clients:client.close()
