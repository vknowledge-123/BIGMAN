"""Real API/storage/scanner workflows with only the external Dhan boundary replaced."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import threading
import time

from fastapi.testclient import TestClient
import pytest

import app.main as main
from app.dhan_scanner import Candle, Instrument, ScannerEngine
from app.storage import ConfigStore
from test_daily_filter import FakeDhan, SESSION, IST, daily_data
from test_staged_scan import clock, prepared


@pytest.fixture
def integration(tmp_path, monkeypatch, clock):
    store = ConfigStore(tmp_path / 'isolated-config.json')
    engine = ScannerEngine(store)
    broker = FakeDhan()
    monkeypatch.setattr(main, 'scanner', engine)
    monkeypatch.setattr(main, 'store', store)
    monkeypatch.setattr(engine, '_client', lambda: broker)
    monkeypatch.setattr(engine.resolver, 'resolve', lambda symbols:
                        ({symbol: Instrument(symbol, str(i+1), symbol) for i, symbol in enumerate(symbols)}, []))
    # Keep real throttle/SDK wrapper paths, but no wall-clock waits in broker simulations.
    monkeypatch.setattr('app.dhan_scanner.time.sleep', lambda _: None)
    with TestClient(main.app) as http:
        assert http.post('/api/credentials', json={'client_id':'test','access_token':'fake'}).status_code == 200
        assert http.post('/api/symbols', json={'symbols_text':'RED\nGREEN'}).status_code == 200
        yield SimpleNamespace(http=http, engine=engine, broker=broker, store=store, clock=clock)


def test_api_cache_settings_repair_backtest_and_restart(integration):
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    assert ctx.http.post('/api/cache-volume').status_code == 200
    assert ctx.http.post('/api/repair').status_code == 200
    assert ctx.http.get('/api/state').json()['stocks'][0]['redwala_gira']
    before = len(ctx.broker.minute_calls) + len(ctx.broker.daily_calls)
    settings = {'daily_volume_max':.001, 'minute_volume_min':99999, 'first_candle_turnover_min':30000000}
    assert ctx.http.post('/api/volume-filters', json=settings).status_code == 200
    assert len(ctx.broker.minute_calls) + len(ctx.broker.daily_calls) == before
    assert all(row['redwala_gira'] for row in ctx.http.get('/api/state').json()['stocks'])
    result = ctx.http.post('/api/backtest', json={'target_date':SESSION.isoformat()})
    assert result.status_code == 200, result.text
    assert result.json()['redwala_count'] == 2
    assert ctx.store.load().volume_filters.minute_volume_min == 99999
    restarted = ScannerEngine(ctx.store)
    restarted.resolver = ctx.engine.resolver
    restarted.load_saved()
    assert restarted.snapshot()['volume_filters']['daily_volume_max'] == .001
    assert len(restarted.snapshot()['stocks']) == 2


def test_redwala_missing_daily_data_retries_and_restores_low_badge(integration):
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    ctx.broker.fail_daily = True
    with pytest.raises(RuntimeError, match='DH-901'):
        ctx.engine.evaluate_opening_candidates(only_pending=True)
    assert ctx.http.get('/api/state').json()['stocks'][0]['redwala_gira']
    ctx.broker.fail_daily = False
    ctx.engine.evaluate_opening_candidates(only_pending=True)
    row = next(row for row in ctx.http.get('/api/state').json()['stocks'] if row['symbol'] == 'RED')
    assert row['daily_filter'] is not None
    assert row['previous_day_low_break']
    assert row['error'] is None


def test_dh905_daily_failure_is_explicit_partial_redwala_result(integration, monkeypatch):
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    calls = []
    def rejected_daily(*args):
        calls.append(args)
        return {'status':'failure','remarks':{'error_code':'DH-905','error_type':'Input_Exception',
                'error_message':'Missing required fields, bad values for parameters etc.'}}
    monkeypatch.setattr(ctx.broker, 'historical_daily_data', rejected_daily)
    response = ctx.http.post('/api/backtest', json={'target_date':SESSION.isoformat()})
    assert response.status_code == 200
    result = response.json()
    assert result['redwala_count'] == result['warning_count'] == 2
    assert result['error_count'] == 0
    assert len(calls) == 2  # Do not blindly retry rejected parameters.
    for row in result['stocks']:
        assert row['redwala_gira'] and row['daily_filter'] is None
        assert not row['previous_day_low_break']
        assert row['status'] == 'Partial: daily history unavailable'
        assert 'Daily history' in row['data_warning'] and 'security ID' in row['data_warning']
        assert 'DH-905' in row['data_warning']


def test_backtest_auth_failure_preserves_redwala_but_stops_remaining_requests(integration):
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    ctx.broker.fail_daily = True
    response = ctx.http.post('/api/backtest', json={'target_date':SESSION.isoformat()})
    assert response.status_code == 200
    result = response.json()
    assert result['redwala_count'] == result['warning_count'] == result['error_count'] == 1
    assert len(ctx.broker.daily_calls) == len(ctx.broker.minute_calls) == 1


def test_retest_does_not_reuse_previous_session_volume_cache(integration):
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    state = prepared('RED')
    state.volume_session = SESSION - timedelta(days=1)
    ctx.engine._states = {'RED':state}
    first = Candle(datetime(2026,10,1,9,15,tzinfo=IST),100,100,95,99,400000)
    following = Candle(first.end,99,101,98,100,1000)
    ctx.engine._apply_opening_candidate('RED', [first, following])
    row = ctx.http.get('/api/state').json()['stocks'][0]
    assert row['redwala_gira']
    assert row['volume_multiplier'] is None
    assert not row['retest_break']


def test_backtest_cannot_qualify_unfinished_first_candle(integration):
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(minute=15,second=30)
    response = ctx.http.post('/api/backtest', json={'target_date':SESSION.isoformat()})
    assert response.status_code == 200
    assert response.json()['qualified_count'] == 0


@pytest.mark.parametrize('field,value', [('open',float('nan')), ('high',float('inf')),
                                        ('volume',-1), ('low',0), ('high',1)])
def test_malformed_broker_candles_never_break_api_or_qualify(integration, monkeypatch, field, value):
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    original = ctx.broker.intraday_minute_data
    def malformed(*args, **kwargs):
        result = original(*args, **kwargs)
        result['data'][field][0] = value
        return result
    monkeypatch.setattr(ctx.broker, 'intraday_minute_data', malformed)
    response = ctx.http.post('/api/backtest', json={'target_date':SESSION.isoformat()})
    assert response.status_code == 200
    assert response.json()['qualified_count'] == 0
    assert response.json()['error_count'] == 2


def test_failed_feed_start_does_not_leave_scanner_running(integration, monkeypatch):
    ctx = integration
    class BrokenFeed:
        NSE='NSE_EQ'
        Quote=17
        def __init__(self,*args,**kwargs): pass
        def start(self): raise RuntimeError('connection refused')
        def close_connection(self): pass
    monkeypatch.setattr('app.dhan_scanner.MarketFeed', BrokenFeed)
    monkeypatch.setattr('app.dhan_scanner.DhanContext', lambda *_: object())
    response = ctx.http.post('/api/start')
    assert response.status_code == 500
    state = ctx.http.get('/api/state').json()
    assert not state['running'] and not state['connected']
    assert 'connection refused' in state['status']




@pytest.mark.parametrize('phase', ['daily', 'minute'])
def test_stopping_during_history_request_cannot_publish_late_candidate(integration, monkeypatch, phase):
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    state = prepared('GREEN', '1')
    if phase == 'daily':
        state.daily_filter = None
    else:
        state.opening_volume_average = None
    ctx.engine._states = {'GREEN':state}
    first = Candle(datetime(2026,10,1,9,15,tzinfo=IST),100,102,99,101,500000)
    monkeypatch.setattr(ctx.engine, '_fetch_opening_candles', lambda *_:[first])
    entered, release = threading.Event(), threading.Event()
    method = 'historical_daily_data' if phase == 'daily' else 'intraday_minute_data'
    original = getattr(ctx.broker, method)
    def slow_history(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(ctx.broker, method, slow_history)
    failures = []
    def confirm():
        try:
            ctx.engine.evaluate_opening_candidates(only_pending=True)
        except Exception as exc:
            failures.append(exc)
    worker = threading.Thread(target=confirm)
    worker.start()
    try:
        assert entered.wait(2)
        assert ctx.http.post('/api/stop').status_code == 200
        release.set()
        worker.join(3)
        assert not worker.is_alive()
        assert not failures
        assert not ctx.http.get('/api/state').json()['stocks'][0]['qualifies_scan']
    finally:
        release.set()
        worker.join(3)


@pytest.mark.parametrize('width', [1366, 390])
def test_browser_real_api_settings_cache_backtest_and_badges(integration, width):
    """Browser -> actual FastAPI -> engine -> fake SDK, with a temporary config."""
    from playwright.sync_api import sync_playwright
    from urllib.parse import urlsplit

    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width':width, 'height':950})
            page.on('pageerror', lambda error: errors.append(str(error)))
            def route(request):
                url = urlsplit(request.request.url)
                if url.hostname != 'scanner.test':
                    request.fulfill(body='')
                    return
                response = ctx.http.request(request.request.method, url.path + ('?' + url.query if url.query else ''),
                    content=request.request.post_data, headers={'Content-Type':'application/json'})
                request.fulfill(status=response.status_code, body=response.content,
                                content_type=response.headers.get('content-type','text/plain'))
            page.route('**/*', route)
            page.goto('http://scanner.test/')
            page.wait_for_function('savedFilterSettings !== null')
            page.locator('#volumeCacheButton').click()
            page.locator('#stockRows').get_by_text('redwala gira', exact=True).first.wait_for()
            assert page.locator('#stockRows').get_by_text('First Candle PDL Cross', exact=True).count() == 2
            assert page.locator('#premarketButton, option[value="premarket"]').count() == 0
            assert page.locator('.live-table thead th').nth(2).inner_text() == '1ST TURNOVER'
            turnover = page.locator('#stockRows .first-turnover-cell').first
            stock = page.locator('#stockRows .symbol-cell').first
            for scroll in (0, 650):
                page.locator('#openingLiveResults').evaluate('(node, x) => { node.scrollLeft = x; }', scroll)
                box = turnover.bounding_box()
                stock_box = stock.bounding_box()
                assert box['x'] >= stock_box['x'] + stock_box['width'] - 1
                assert box['x'] + box['width'] <= width
            page.locator('#openingLiveResults').evaluate('(node) => { node.scrollLeft = 0; }')
            page.locator('#dailyVolumeMax').fill('0.01')
            page.locator('#minuteVolumeMin').fill('99999')
            page.locator('#saveVolumeFilters').click()
            page.wait_for_function('savedFilterSettings.minute_volume_min === 99999')
            assert ctx.store.load().volume_filters.minute_volume_min == 99999
            page.locator('#setupFilter').select_option('redwala')
            assert page.locator('#stockRows').get_by_text('redwala gira', exact=True).count() == 2
            page.locator('#firstCandleTurnoverMin').fill('1000')
            page.locator('#saveVolumeFilters').click()
            page.wait_for_function('lastLiveState.stocks.every(row => !row.redwala_gira)')
            # Run Backtest must apply the newly typed turnover value through the API.
            page.locator('#firstCandleTurnoverMin').fill('3')
            page.locator('#backtestTab').click()
            page.locator('#backtestDate').fill(SESSION.isoformat())
            page.locator('#backtestButton').click()
            page.locator('#backtestRows').get_by_text('redwala gira', exact=True).first.wait_for()
            assert ctx.store.load().volume_filters.first_candle_turnover_min == 30000000
            assert page.locator('#backtestRows').get_by_text('First Candle PDL Cross', exact=True).count() == 2
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors
        finally:
            browser.close()
