from datetime import datetime, timedelta

import pytest

from app.dhan_scanner import Candle, StockState, Instrument
from app.schemas import VolumeFilterSettings
from test_daily_filter import SESSION, IST
from test_staged_scan import engine, clock, prepared


def first(volume=400000):
    return Candle(datetime(2026, 10, 1, 9, 15, tzinfo=IST), 100, 100, 95, 99, volume)


@pytest.mark.parametrize('volume,matched', [(300000, False), (303030, False), (400000, True)])
@pytest.mark.parametrize('history', ['missing', 'failed', 'passing'])
def test_redwala_only_turnover_even_without_minute_samples(engine, clock, volume, matched, history):
    state = prepared('A')
    state.opening_volume_average = None
    state.opening_volume_samples = []
    if history == 'missing':
        state.daily_filter = None
    elif history == 'failed':
        state.daily_filter['passes'] = False
    engine._states = {'A': state}
    bar = first(volume)
    engine._apply_opening_candidate('A', [bar])
    live = engine.snapshot()['stocks'][0]
    backtest = engine._build_backtest_row(state.instrument, SESSION, [bar], state.daily_filter)
    for row in (live, backtest):
        assert row['redwala_gira'] is matched
        assert row['volume_multiplier'] is None
        assert not row['possible_candidate'] and not row['retest_break']
    engine.update_volume_filters(VolumeFilterSettings(daily_volume_max=.01, minute_volume_min=99999))
    assert engine.snapshot()['stocks'][0]['redwala_gira'] is matched


def test_turnover_equality_fails_and_saving_turnover_rechecks_without_network(engine, clock, monkeypatch):
    state = StockState(Instrument('A', '1', 'A'))
    engine._states = {'A': state}
    bar = first()
    engine._apply_opening_candidate('A', [bar])
    monkeypatch.setattr(engine, '_client', lambda: pytest.fail('No requests on Save'))
    engine.update_volume_filters(VolumeFilterSettings(first_candle_turnover_min=bar.turnover))
    assert not state.redwala_gira
    engine.update_volume_filters(VolumeFilterSettings(first_candle_turnover_min=bar.turnover - 1))
    assert state.redwala_gira


def test_daily_and_minute_fetch_errors_do_not_hide_redwala(engine, clock, monkeypatch):
    state = StockState(Instrument('A', '1', 'A'))
    engine._states = {'A': state}
    monkeypatch.setattr(engine, '_fetch_opening_candles', lambda *_: [first()])
    monkeypatch.setattr(engine, '_fetch_daily_filter', lambda *_: (_ for _ in ()).throw(RuntimeError('daily missing')))
    engine.evaluate_opening_candidates(only_pending=True)
    assert state.redwala_gira and state.confirmation_status == 'confirmed'
    monkeypatch.setattr(engine, '_fetch_backtest_history', lambda *_: [first()])
    result = engine.backtest_date(SESSION)
    assert result['redwala_count'] == 1


@pytest.mark.parametrize('low,first_break,pdl_break', [(95, False, False), (94, True, False), (93.99, True, True)])
def test_low_badges_strict_thresholds_and_backtest_parity(engine, clock, low, first_break, pdl_break):
    clock[0] = clock[0].replace(hour=10)
    state = prepared('A')
    state.daily_filter['previous_low'] = 94
    state.opening_volume_average = None
    engine._states = {'A': state}
    bar = first()
    later = Candle(bar.end, 99, 100, low, 99, 100)
    engine._apply_opening_candidate('A', [bar, later])
    rows = [engine.snapshot()['stocks'][0], engine._build_backtest_row(state.instrument, SESSION, [bar, later], state.daily_filter)]
    for row in rows:
        assert row['first_candle_low_break'] is first_break
        assert row['previous_day_low_break'] is pdl_break
    # A rebound must not erase historical breaks.
    rebound = Candle(later.end, 100, 102, 100, 101, 100)
    engine._apply_opening_candidate('A', [bar, rebound])
    assert engine.snapshot()['stocks'][0]['first_candle_low_break'] is first_break


def test_ticks_break_lows_without_cumulative_volume_and_latch_after_rebound(engine, clock):
    state = prepared('A')
    state.daily_filter['previous_low'] = 94
    engine._states = {'A': state}
    engine._security_symbols = {'1': 'A'}
    engine._apply_opening_candidate('A', [first()])
    def tick(price):
        engine._on_message(None, {'security_id': '1', 'LTP': price, 'LTT': '09:16:02'})
    clock[0] = clock[0].replace(minute=16, second=2)
    tick(95)
    assert not engine.snapshot()['stocks'][0]['first_candle_low_break']
    tick(93)
    tick(101)
    row = engine.snapshot()['stocks'][0]
    assert row['first_candle_low_break'] and row['previous_day_low_break']
    state.confirmed_opening_candle = Candle(first().start + timedelta(days=1), 100, 100, 95, 99, 400000)
    assert not engine.snapshot()['stocks'][0]['first_candle_low_break']
    assert not engine.snapshot()['stocks'][0]['previous_day_low_break']


def test_missing_previous_low_suppresses_only_pdl_badge(engine, clock):
    state = StockState(Instrument('A', '1', 'A'))
    engine._states = {'A': state}
    bar = first()
    engine._apply_opening_candidate('A', [bar, Candle(bar.end, 99, 100, 93, 94, 1)])
    row = engine.snapshot()['stocks'][0]
    assert row['redwala_gira'] and row['first_candle_low_break']
    assert not row['previous_day_low_break']


def test_daily_failed_red_live_preview_not_rejected_by_minute_volume(engine, clock):
    clock[0] = clock[0].replace(minute=16)
    state = prepared('A')
    state.daily_filter['passes'] = False
    state.current_candle = first()
    state.opening_volume_average = 10000000
    engine._states = {'A': state}
    engine._screen_live_opening(SESSION)
    assert state.provisional_setup == 'redwala gira'
    assert state.confirmation_status == 'awaiting_confirmation'


def test_bulk_cache_failure_keeps_only_current_confirmed_redwala(engine, clock, monkeypatch):
    state = StockState(Instrument('A', '1', 'A'))
    engine._states = {'A': state}
    engine._apply_opening_candidate('A', [first()])
    monkeypatch.setattr(engine, '_fetch_daily_filter', lambda *_: (_ for _ in ()).throw(RuntimeError('DH-901')))
    with pytest.raises(RuntimeError, match='DH-901'):
        engine.cache_opening_volume_averages()
    assert state.redwala_gira
    clock[0] += timedelta(days=1)
    with pytest.raises(RuntimeError, match='DH-901'):
        engine.cache_opening_volume_averages()
    assert not state.redwala_gira
