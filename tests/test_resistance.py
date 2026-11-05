from datetime import datetime, timedelta
from copy import deepcopy
from urllib.parse import urlsplit
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import resistance
from app.daily_filter import calculate_daily_filter
from app.dhan_scanner import Candle, ScannerEngine
from app.schemas import VolumeFilterSettings
from app.storage import ConfigStore
from test_staged_scan import SESSION, IST, clock, engine, prepared
from test_integration_workflows import integration
from test_algo import env
from app.algo_strategy import AlgoBacktest, AlgoSettings


def history():
    days, day = [], SESSION - timedelta(days=1)
    while len(days) < 10:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return [dict(date=day.isoformat(), open=high-2, high=high, low=high-4, close=high-1, volume=100000)
            for day, high in zip(reversed(days), [90, 92, 94, 105, 100, 98, 97, 99, 100, 101])]


def daily():
    return {**prepared('A').daily_filter, 'previous_close':100,
            'resistance_history':history(), 'resistance_capacity':62}


def settings(**kwargs):
    return VolumeFilterSettings(resistance_filter=True, **kwargs)


def bars(first_close=102):
    first = Candle(datetime.combine(SESSION, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15),
                   99, max(103, first_close), 98, first_close, 400000)
    second = Candle(first.end, 104, 107, 103, 106, 10000)
    return [first, second]


def prior(first):
    return [Candle(first.start - timedelta(days=n), 99, 101, 98, 100, 100000) for n in (1, 2, 3)]


def test_short_listing_history_selects_confirmed_peak_and_counts_trading_days():
    result = resistance.selection(daily(), SESSION, settings())
    assert result['resistance_level'] == result['resistance_threshold'] == 105
    assert result['resistance_age'] == 7
    assert result['resistance_date'] == history()[3]['date']
    assert result['resistance_pullback_percent'] == pytest.approx(100 * 12 / 105)


@pytest.mark.parametrize('changes,expected', [
    ({'resistance_min_age':7, 'resistance_max_age':7}, 'ready'),
    ({'resistance_min_age':8}, 'no_level'),
    ({'resistance_max_age':6}, 'no_level'),
    ({'resistance_lookback':6, 'resistance_max_age':6}, 'no_level'),
    ({'resistance_pullback':True, 'resistance_pullback_min':12}, 'no_level'),
    ({'resistance_pullback':True, 'resistance_pullback_min':10}, 'ready'),
])
def test_age_lookback_pullback(changes, expected):
    assert resistance.selection(daily(), SESSION, settings(**changes))['resistance_status'] == expected


@pytest.mark.parametrize('corruption', ['stale', 'future', 'duplicate', 'missing', 'capacity', 'bad_high', 'nan'])
def test_missing_or_invalid_history_is_pending_not_no_level(corruption):
    d = daily()
    if corruption == 'stale': d['session_date'] = '2020-01-01'
    if corruption == 'future': d['resistance_history'][-1]['date'] = SESSION.isoformat()
    if corruption == 'duplicate': d['resistance_history'][1]['date'] = d['resistance_history'][0]['date']
    if corruption == 'missing': d.pop('resistance_history')
    if corruption == 'capacity': d['resistance_capacity'] = 0
    if corruption == 'bad_high': d['resistance_history'][0]['high'] = 1
    if corruption == 'nan': d['resistance_history'][0]['high'] = float('nan')
    assert resistance.selection(d, SESSION, settings())['resistance_status'] == 'unresolved'
    assert resistance.selection(d, SESSION, VolumeFilterSettings())['resistance_status'] == 'off'


def test_confirmation_no_future_peaks_equal_highs_and_retired_levels():
    d = daily()
    d['resistance_history'][-2].update(high=120, close=100)
    assert resistance.selection(d, SESSION, settings())['resistance_level'] == 105  # Not enough right candles.
    d = daily()
    d['resistance_history'][4].update(high=105)
    assert resistance.selection(d, SESSION, settings())['resistance_status'] == 'no_level'  # Strict swing.
    d = daily()
    d['resistance_history'][7].update(high=110, close=106)
    assert resistance.selection(d, SESSION, settings())['resistance_status'] == 'no_level'


def test_nearest_overhead_peak_and_strict_buffer():
    d = daily()
    d['resistance_history'][6].update(high=110, close=100)
    selected = resistance.selection(d, SESSION, settings(resistance_buffer=.5))
    assert selected['resistance_level'] == 105
    assert selected['resistance_threshold'] == 105.525
    assert not resistance.above(105.525, selected)
    assert resistance.above(105.526, selected)


@pytest.mark.parametrize('invalid', [dict(resistance_lookback=0), dict(resistance_min_age=61),
    dict(resistance_max_age=61), dict(resistance_right=60), dict(resistance_buffer=float('inf')),
    dict(resistance_lookback=60.5), dict(resistance_pullback_min=-1)])
def test_settings_validation(invalid):
    with pytest.raises(ValidationError): settings(**invalid)


def test_daily_history_excludes_today_and_persists_raw_ohlc():
    rows = history() + [{**history()[-1], 'date':SESSION.isoformat(), 'high':999}]
    payload = {key:[row[key] for row in rows] for key in ('open','high','low','close','volume')}
    payload['timestamp'] = [datetime.fromisoformat(row['date']).replace(tzinfo=IST).timestamp() for row in rows]
    result = calculate_daily_filter(payload, SESSION, resistance_capacity=62)
    assert result['resistance_history'] == history()
    assert resistance.selection(result, SESSION, settings())['resistance_level'] == 105


def test_live_later_cross_without_fetch_and_badges_scope(engine, monkeypatch, clock):
    state = prepared('A')
    state.daily_filter = daily()
    engine._states = {'A':state}
    engine.update_volume_filters(settings())
    first, second = bars()
    clock[0] = first.end + timedelta(seconds=1)
    engine._apply_opening_candidate('A', [first])
    assert not state.possible_candidate and state.confirmation_status == 'confirmed'
    monkeypatch.setattr(engine, '_client', lambda: pytest.fail('Tick must not fetch'))
    engine._on_message(None, {'security_id':'1','LTP':106,'volume':410000,'LTT':'09:16:05'})
    assert state.possible_candidate
    state.current_candle = second
    row = engine.snapshot()['stocks'][0]
    assert row['resistance_break'] and row['resistance_break_open']
    assert row['resistance_break_open_candle'] == 2
    engine._on_message(None, {'security_id':'1','LTP':105,'volume':410001,'LTT':'09:16:06'})
    assert not state.possible_candidate  # Current-LTP filter; equality is not a break.
    engine.update_volume_filters(VolumeFilterSettings())
    assert state.possible_candidate
    assert not engine.snapshot()['stocks'][0].get('resistance_break', False)


@pytest.mark.parametrize('candle_index', [1,2,3])
def test_backtest_later_green_close_and_first_two_open_cross(engine, clock, candle_index):
    engine.update_volume_filters(settings())
    first, second = bars(106 if candle_index == 1 else 102)
    if candle_index == 3:
        second.close = 104
    third = Candle(second.end, 104, 107, 103, 106, 10000)
    session = [first] + ([] if candle_index == 1 else [second]) + ([third] if candle_index == 3 else [])
    clock[0] = third.end
    result = engine._build_backtest_row(prepared('A').instrument, SESSION, prior(first)+session, daily())
    assert result['possible_candidate'] and result['resistance_break']
    assert result['resistance_break_open'] is (candle_index < 3)
    assert result['resistance_break_open_candle'] == (candle_index if candle_index < 3 else None)
    assert result['resistance_break_at'] == session[-1].end.isoformat()
    # An algo entry before the breakout must not see later candles.
    if candle_index > 1:
        early = engine._build_backtest_row(prepared('A').instrument, SESSION, prior(first)+[first], daily())
        assert not early['possible_candidate']


def test_replay_ignores_wicks_red_closes_and_equality(engine, clock):
    engine.update_volume_filters(settings())
    first, second = bars()
    second.open, second.high, second.close = 108, 109, 106  # Red close above is not confirmation.
    third = Candle(second.end, 104, 110, 103, 105, 10000)
    clock[0] = third.end
    result = engine._build_backtest_row(prepared('A').instrument, SESSION, prior(first)+[first,second,third], daily())
    assert not result['possible_candidate']


def test_redwala_and_retest_unaffected_by_missing_resistance(engine, clock):
    engine.update_volume_filters(settings())
    first, second = bars()
    first.open, first.high, first.close = 103, 103, 100
    second.open, second.close = 100, 104
    clock[0] = second.end
    row = engine._build_backtest_row(prepared('A').instrument, SESSION, prior(first)+[first,second], None)
    assert row['redwala_gira']
    row = engine._build_backtest_row(prepared('A').instrument, SESSION, prior(first)+[first,second], prepared('A').daily_filter)
    assert row['retest_break']
    assert not row.get('resistance_break', False)


def test_old_cache_refresh_once_and_no_peak_is_not_retried(engine, monkeypatch):
    state = prepared('A')
    engine._states = {'A':state}
    engine.update_volume_filters(settings())
    calls = []
    d = daily()
    for i, row in enumerate(d['resistance_history']): row.update(high=100+i, close=99+i, low=98+i)
    monkeypatch.setattr(engine, '_fetch_daily_filter', lambda *_: calls.append(1) or deepcopy(d))
    engine._prepare_daily(object(), state, SESSION)
    engine._prepare_daily(object(), state, SESSION)
    assert calls == [1]
    assert resistance.selection(state.daily_filter, SESSION, settings())['resistance_status'] == 'no_level'
    saved = ConfigStore(engine.store.path).load().opening_volume_cache['A']['daily_filter']
    assert saved['resistance_capacity'] == 62


def test_daily_fetch_extends_one_request_and_reuses_cached_selection(engine, monkeypatch):
    engine.update_volume_filters(settings())
    rows = history()
    payload = {key:[row[key] for row in rows] for key in ('open','high','low','close','volume')}
    payload['timestamp'] = [datetime.fromisoformat(row['date']).replace(tzinfo=IST).timestamp() for row in rows]
    calls = []
    monkeypatch.setattr(engine, '_historical_daily_with_retry', lambda *args: calls.append(args) or {'status':'success', 'data':payload})
    d = engine._fetch_daily_filter(object(), prepared('A').instrument, SESSION)
    assert len(calls) == 1
    assert calls[0][-2:] == ((SESSION-timedelta(days=154)).isoformat(), SESSION.isoformat())
    hits = resistance._select.cache_info().hits
    assert resistance.selection(d, SESSION, settings())['resistance_level'] == 105
    assert resistance._select.cache_info().hits > hits


def test_missing_resistance_remains_pending_even_with_volume_cache(engine, monkeypatch):
    state = prepared('A')
    engine._states = {'A':state}
    engine.update_volume_filters(settings())
    calls = []
    monkeypatch.setattr(engine, '_fetch_daily_filter', lambda *_:calls.append(1) or prepared('A').daily_filter)
    assert engine.cache_opening_volume_averages() == {}
    assert calls == [1,1,1]
    assert state.preparation_status == 'unresolved'
    assert 'resistance data pending' in state.error
    engine.update_volume_filters(VolumeFilterSettings())
    assert state.error is None and state.preparation_status == 'ready'


def test_live_resistance_uses_fresh_quote_price_without_websocket(engine, clock):
    state = prepared('A')
    state.daily_filter = daily()
    engine._states = {'A':state}
    engine.update_volume_filters(settings())
    first, second = bars(106)
    clock[0] = second.end
    engine._apply_opening_candidate('A', [first])
    state.ltp, state.ltp_updated_at = 104, clock[0]
    assert not engine.snapshot()['stocks'][0]['possible_candidate']
    state.ltp = 106
    assert engine.snapshot()['stocks'][0]['possible_candidate']


def test_algo_replay_cannot_enter_before_resistance_confirmation(env, monkeypatch, clock):
    service, _ = env
    engine = service.engine
    engine._volume_filters = settings()
    first, second = bars()
    third = Candle(second.end, 106, 107, 105, 106.5, 10000)
    clock[0] = third.end + timedelta(minutes=1)
    monkeypatch.setattr(service, 'now', lambda:clock[0])
    instrument = engine._states['AAA'].instrument
    monkeypatch.setattr(engine.resolver, 'resolve', lambda *_:({'AAA':instrument},[]))
    monkeypatch.setattr(engine, '_client', lambda:None)
    monkeypatch.setattr(engine, '_fetch_backtest_history', lambda *_:prior(first)+[first,second,third])
    monkeypatch.setattr(engine, '_fetch_daily_filter', lambda *_:daily())
    with pytest.raises(ValueError, match='does not qualify'):
        service.backtest(AlgoBacktest(symbol='AAA', setup='possible', target_date=SESSION, start_time='09:16'))
    result = service.backtest(AlgoBacktest(symbol='AAA', setup='possible', target_date=SESSION,
        start_time='09:17', settings=AlgoSettings(mode='live')))
    assert result['qualification']['resistance_break_open_candle'] == 2
    assert result['strategy']['settings']['mode'] == 'paper'


def test_browser_settings_persistence_badges_and_backtest(integration, monkeypatch):
    pw = pytest.importorskip('playwright.sync_api')
    ctx = integration
    first, second = bars()
    ctx.clock[0] = second.end + timedelta(seconds=1)
    state = prepared('GREEN')
    state.daily_filter = daily()
    ctx.engine._states = {'GREEN':state}
    ctx.engine._apply_opening_candidate('GREEN',[first, second])
    state.ltp, state.last_tick_time = 106, ctx.clock[0]
    monkeypatch.setattr(ctx.engine, '_fetch_backtest_history', lambda *_: prior(first)+[first,second])
    monkeypatch.setattr(ctx.engine, '_fetch_daily_filter', lambda *_: daily())
    def route(r):
        url = urlsplit(r.request.url)
        if url.hostname != 'scanner.test':
            r.abort(); return
        result = ctx.http.request(r.request.method, url.path, content=r.request.post_data,
                                  headers={'content-type':'application/json'})
        r.fulfill(status=result.status_code, body=result.content, content_type=result.headers.get('content-type','text/html'))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width':1440,'height':1000})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('**/*',route)
            page.goto('http://scanner.test/')
            pw.expect(page.locator('#saveVolumeFilters')).to_be_enabled()
            page.locator('#resistanceFilter').check()
            page.locator('#resistanceBuffer').fill('0.25')
            page.locator('#saveVolumeFilters').click()
            pw.expect(page.locator('#activeVolumeFilters')).to_contain_text('Daily Resistance ON')
            pw.expect(page.locator('#stockRows')).to_contain_text('resistance_break_open')
            assert ctx.store.load().volume_filters.resistance_buffer == .25
            page.reload()
            pw.expect(page.locator('#resistanceFilter')).to_be_checked()
            pw.expect(page.locator('#resistanceBuffer')).to_have_value('0.25')
            page.locator('#backtestTab').click()
            page.locator('#backtestDate').fill(SESSION.isoformat())
            page.locator('#backtestButton').click()
            pw.expect(page.locator('#backtestButton')).to_be_enabled()
            pw.expect(page.locator('#backtestRows')).to_contain_text('resistance_break_open')
            artifacts = Path('docs/algo-test-artifacts')
            artifacts.mkdir(parents=True, exist_ok=True)
            page.locator('#resistanceFilter').scroll_into_view_if_needed()
            page.screenshot(path=str(artifacts/'resistance-settings-desktop.png'))
            page.set_viewport_size({'width':390,'height':844})
            page.locator('#resistanceFilter').scroll_into_view_if_needed()
            page.screenshot(path=str(artifacts/'resistance-settings-mobile.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            assert not errors
        finally:
            browser.close()
