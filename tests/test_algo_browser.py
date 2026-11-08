"""Headless Edge UI + real FastAPI handlers; fake quotes/history, no broker I/O."""
import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.algo_service import AlgoService
from app.dhan_scanner import Candle, IST, Instrument, ScannerEngine, StockState
from app.storage import ConfigStore


@pytest.mark.parametrize('hour', [10, 14])
@pytest.mark.parametrize('direction', ['setup', 'long'])
@pytest.mark.parametrize('setup', ['possible', 'redwala'])
def test_browser_selected_stock_paper_exit_backtest(tmp_path, monkeypatch, hour, direction, setup):
    pw = pytest.importorskip('playwright.sync_api')
    import app.main as main
    engine = ScannerEngine(ConfigStore(tmp_path/'config.json'))
    engine.store.update_credentials('TEST', 'FAKE_TOKEN')
    now = datetime(2026,10,16,hour,0,tzinfo=IST)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz else now.replace(tzinfo=None)
    monkeypatch.setattr('app.dhan_scanner.datetime', Clock)
    first = now.replace(hour=9,minute=15)
    instrument=Instrument('AAA','1','Test stock')
    possible = setup == 'possible'
    first_bar = Candle(first,100,101 if possible else 100,100 if possible else 98,101 if possible else 99,400000)
    state=StockState(instrument,signal_session=now.date(),confirmation_status='confirmed',
        possible_candidate=possible,redwala_gira=not possible,qualifies_scan=True,ltp=99,previous_close=100,
        opening_candles=[first_bar])
    engine._states={'AAA':state}
    service=AlgoService(engine); engine._algo=service
    monkeypatch.setattr(service,'now',lambda:now)
    monkeypatch.setattr(service,'_launch',lambda:None)
    monkeypatch.setattr(main,'scanner',engine); monkeypatch.setattr(main,'store',engine.store)
    monkeypatch.setattr(engine.resolver,'resolve',lambda symbols:({'AAA':instrument},[]))
    monkeypatch.setattr(engine,'_client',lambda:None)
    yesterday=first-timedelta(days=1)
    bars=[Candle(yesterday,first_bar.open,first_bar.high,first_bar.low,first_bar.close,400000)] + [Candle(yesterday+timedelta(minutes=i),99,99,99,99,100) for i in range(1,5)]
    if possible:
        from app.daily_filter import calculate_daily_filter
        bars += [Candle(yesterday-timedelta(days=i),100,101,99,100,100) for i in (1,2,3)]
        daily = calculate_daily_filter({'timestamp': [(yesterday-timedelta(days=i)).timestamp() for i in (6,3,2,1)],
            'open': [99]*4, 'close': [100]*4, 'high': [101]*4, 'low': [98]*4, 'volume': [1000]*4}, yesterday.date())
        monkeypatch.setattr(engine,'_fetch_daily_filter',lambda *args:daily)
    monkeypatch.setattr(engine,'_fetch_backtest_history',lambda *args:bars)
    broker=SimpleNamespace(account='TEST')
    client=TestClient(main.app)
    calls=[]
    def route(request):
        url=request.request.url
        path='/' + url.split('://',1)[1].split('/',1)[1]
        if path.startswith('/api/'):
            method=request.request.method
            body=request.request.post_data
            response=client.request(method,path,content=body,headers={'content-type':'application/json'})
            calls.append((path,body))
            if path=='/api/algo/start' and response.status_code==200:
                row=deepcopy(service.records[response.json()['session_id']])
                assert row['mode']=='paper', 'No live execution in browser tests'
                service.step(row,broker,{'bid':99,'ask':99,'time':now.isoformat()})
            if path.endswith('/exit') and response.status_code==200:
                sid=path.split('/')[-2]
                service.step(deepcopy(service.records[sid]),broker,{'bid':99,'ask':99,'time':now.isoformat()})
            request.fulfill(status=response.status_code,body=response.content,content_type='application/json')
        else:
            response=client.get(path)
            request.fulfill(status=response.status_code,body=response.content,content_type=response.headers.get('content-type','text/html'))
    try:
        with pw.sync_playwright() as playwright:
            browser=playwright.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.add_init_script("localStorage.setItem('scanner.dashboardCircuit.v1', 'false')")  # Unrelated fixtures lack circuit quotes.
            errors=[]; page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('https://unpkg.com/**',lambda r:r.abort())
            page.route('http://algo.test/**',route)
            page.goto('http://algo.test/')
            button=page.locator('#stockRows button[data-algo-action="start"]')
            button.wait_for()
            assert page.locator('#openingLiveResults').is_visible()
            assert page.locator('#afternoonStartButton, #afternoonBacktestButton, #afternoonLiveResults').count() == 0
            assert page.locator('#algoMode').input_value()=='paper'
            page.locator('#algoCapital').fill('50000')
            page.locator('#algoFirstDirection').select_option(direction)
            page.locator('#algoLadder').check()
            page.locator('#algoPyramid').check()
            page.locator('#algoSave').click()
            pw.expect(page.locator('#algoMessage')).to_contain_text('defaults saved')
            button.click()
            long_first = direction == 'long' or (direction == 'setup' and possible)
            pw.expect(page.locator('#algoSessions')).to_contain_text('App quantity ' + ('505' if long_first else '-505'))
            pw.expect(page.locator('#algoSessions')).to_contain_text('Pyramiding on')
            page.locator('#algoSessions details summary').click()
            assert page.locator('#algoSessions tbody tr').count()==1
            page.locator('#algoSessions button[data-algo-action="exit"]').click()
            pw.expect(page.locator('#algoSessions')).to_contain_text('App quantity 0')
            pw.expect(page.locator('#algoSessions')).to_contain_text('done')
            # A cancelled live confirmation must never reach the server.
            count=sum(path=='/api/algo/start' for path,_ in calls)
            page.locator('#algoMode').select_option('live')
            page.once('dialog',lambda dialog:dialog.dismiss())
            button.click()
            assert sum(path=='/api/algo/start' for path,_ in calls)==count
            page.locator('#algoBacktestSymbol').fill('AAA')
            page.locator('#algoBacktestSetup').select_option(setup)
            page.locator('#algoBacktestDate').fill('2026-10-15')
            page.locator('#algoBacktestRun').click()
            pw.expect(page.locator('#algoBacktestResult')).to_contain_text('P&L')
            pw.expect(page.locator('#algoBacktestResult')).to_contain_text('Gross P&L')
            pw.expect(page.locator('#algoBacktestResult')).to_contain_text('Cumulative gross P&L')
            pw.expect(page.locator('#algoBacktestResult')).to_contain_text('Backtest-only candle-close reversals')
            pw.expect(page.locator('#algoBacktestResult')).to_contain_text('Initial entry candle: use only its close')
            pw.expect(page.locator('#algoBacktestResult')).to_contain_text('INCOMPLETE SESSION')
            backtest_request=json.loads(next(body for path,body in calls if path=='/api/algo/backtest'))
            assert backtest_request['settings']['mode']=='paper'
            assert backtest_request['settings']['reference']=='original'
            assert backtest_request['settings']['first_direction']==direction
            pw.expect(page.locator('#algoBacktestResult')).to_contain_text('First ladder: ' + ('Long' if long_first else 'Short'))
            pw.expect(page.locator('#algoBacktestStale')).to_be_hidden()
            page.locator('#algoFee').fill('7')
            pw.expect(page.locator('#algoBacktestStale')).to_contain_text('rerun the algo backtest')
            page.locator('#algoBacktestRun').click()
            pw.expect(page.locator('#algoBacktestStale')).to_be_hidden()
            pw.expect(page.locator('#algoBacktestResult')).to_contain_text('costs ₹14.00')
            assert not errors
            artifacts=Path('docs/algo-test-artifacts'); artifacts.mkdir(exist_ok=True)
            page.locator('#algoPanel').screenshot(path=str(artifacts/'algo-desktop.png'))
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.locator('#algoPanel').screenshot(path=str(artifacts/'algo-mobile.png'))
            browser.close()
    finally:
        service.shutdown()
