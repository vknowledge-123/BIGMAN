from datetime import datetime, timedelta
import threading

import pytest

from app.daily_filter import calculate_daily_filter
from app.dhan_scanner import Candle
from app.opening_patterns import retest_sequence
from app.schemas import VolumeFilterSettings
from test_daily_filter import IST, SESSION
from test_open_cross import close_history
from test_staged_scan import clock, engine, prepared


def first_bar(color="red", volume=500_000):
    return Candle(datetime(2026, 10, 1, 9, 15, tzinfo=IST), 200, 202, 198,
                  199 if color == "red" else 201, volume)


def follow(first, colors="ggg", break_index=2):
    bars = []
    for index, color in enumerate(colors):
        close = {"g": 200, "r": 198, "d": 199}[color]
        bars.append(Candle(first.end + timedelta(minutes=index), 199,
                           203 if index == break_index else 201, 197, close, 1000))
    return bars


def seed(engine, first):
    state = prepared("A", "1")
    state.daily_filter = calculate_daily_filter(close_history(), SESSION)
    engine._states = {"A": state}
    engine._apply_opening_candidate("A", [first])
    return state


def as_data(bars):
    return {"timestamp": [bar.start.timestamp() for bar in bars],
            **{key: [getattr(bar, key) for bar in bars] for key in ("open", "high", "low", "close", "volume")}}


@pytest.mark.parametrize("colors,break_index,status", [
    ("g", 0, "confirmed"), ("ggg", 2, "confirmed"), ("gggggggg", 7, "confirmed"),
    ("ggg", 8, "waiting"), ("rg", 1, "rejected"), ("gdg", 2, "rejected"),
    ("ggd", 2, "rejected"), ("gr", 1, "rejected"),
    ("grr", 0, "confirmed"),  # Later red candles cannot undo a confirmed break.
])
def test_retest_sequence(colors, break_index, status):
    first = first_bar()
    result = retest_sequence(first, [first] + follow(first, colors, break_index))
    assert result["retest_status"] == status
    assert result["retest_break"] is (status == "confirmed")


def test_equality_and_missing_minutes_do_not_confirm():
    first = first_bar()
    bars = follow(first, "ggg", 2)
    bars[-1].high = first.high
    assert not retest_sequence(first, bars)["retest_break"]
    bars[-1].high += 0.01
    assert retest_sequence(first, bars)["retest_break"]
    assert retest_sequence(first, [bars[0], bars[2]])["retest_status"] == "unresolved"
    assert retest_sequence(first, bars[1:])["retest_status"] == "unresolved"


def test_live_and_backtest_retest_after_fifth_candle_without_open_high(engine, monkeypatch, clock):
    clock[0] = clock[0].replace(hour=10)
    first = first_bar()
    state = seed(engine, first)
    candles = [first] + follow(first, "gggggggg", 7)
    engine._apply_opening_candidate("A", candles)
    assert state.retest_break and state.qualifies_scan
    assert not state.possible_candidate and not state.redwala_gira
    assert len(state.opening_candles) == 5  # Display stays compact, scan sees later bars.
    history = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)]
    monkeypatch.setattr(engine, "_fetch_backtest_history", lambda *_: history + candles)
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: state.daily_filter)
    result = engine.backtest_date(SESSION)
    assert result["retest_count"] == result["qualified_count"] == 1
    assert result["candidate_count"] == result["redwala_count"] == 0
    assert result["stocks"][0]["retest_break_at"] == state.retest_break_at
    assert result["stocks"][0]["first_candle_turnover"] == first.volume * first.close


@pytest.mark.parametrize("settings,qualifies", [
    (VolumeFilterSettings(), True),
    (VolumeFilterSettings(minute_volume_min=6), False),
    (VolumeFilterSettings(first_candle_turnover_min=100_000_000), False),
    (VolumeFilterSettings(daily_volume_max=0.5), True),  # Existing negative price exception.
    (VolumeFilterSettings(today_open_cross=True), True),
])
def test_retest_uses_saved_filters_and_settings_reapply_history(engine, settings, qualifies):
    first = first_bar()
    state = seed(engine, first)
    engine._apply_opening_candidate("A", [first] + follow(first, "g", 0))
    engine.update_volume_filters(settings)
    assert state.retest_break is qualifies
    assert state.qualifies_scan is qualifies


def test_retest_open_cross_does_not_change_redwala(engine):
    first = first_bar()
    first.open = first.high = 199  # Touches the cached highest close, not greater.
    first.close = 198
    state = seed(engine, first)
    engine._apply_opening_candidate("A", [first] + follow(first, "g", 0))
    assert state.retest_break and state.redwala_gira
    engine.update_volume_filters(VolumeFilterSettings(today_open_cross=True))
    assert not state.retest_break
    assert state.redwala_gira and state.qualifies_scan
    assert state.retest_status == "filtered"


def test_retest_daily_filter_failure_cannot_qualify(engine):
    first = first_bar()
    state = seed(engine, first)
    state.daily_filter["passes"] = False
    engine._apply_opening_candidate("A", [first] + follow(first, "g", 0))
    assert not state.retest_break and not state.qualifies_scan


def test_live_high_break_uses_later_ltp_is_strict_and_latches(engine, clock):
    first = first_bar("green")
    state = seed(engine, first)
    clock[0] = clock[0].replace(hour=9, minute=16, second=5)
    def tick(price, time="09:16:05"):
        engine._on_message(None, {"security_id": "1", "LTP": price, "LTT": time, "volume": 600_000})
    tick(203, "09:15:59")
    assert not engine.snapshot()["stocks"][0]["first_candle_high_break"]
    tick(202)
    assert not engine.snapshot()["stocks"][0]["first_candle_high_break"]
    tick(202.01)
    assert engine.snapshot()["stocks"][0]["first_candle_high_break"]
    tick(190, "09:16:06")
    assert engine.snapshot()["stocks"][0]["first_candle_high_break"]
    engine.update_volume_filters(VolumeFilterSettings(minute_volume_min=6))
    assert not engine.snapshot()["stocks"][0]["first_candle_high_break"]


def test_high_break_in_backtest_and_not_for_red_first(engine, clock):
    clock[0] = clock[0].replace(hour=10)
    first = first_bar("green")
    state = seed(engine, first)
    history = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)]
    bars = [first] + follow(first, "g", 0)
    row = engine._build_backtest_row(state.instrument, SESSION, history + bars, state.daily_filter)
    assert row["first_candle_high_break"]
    first.close = 199
    row = engine._build_backtest_row(state.instrument, SESSION, history + bars, state.daily_filter)
    assert row["retest_break"] and not row["first_candle_high_break"]


def test_worker_only_fetches_eligible_red_and_ignores_forming_bar(engine, monkeypatch, clock):
    first = first_bar()
    state = seed(engine, first)
    green = prepared("G", "2")
    engine._states["G"] = green
    engine._apply_opening_candidate("G", [first_bar("green")])
    low = prepared("L", "3")
    engine._states["L"] = low
    engine._apply_opening_candidate("L", [first_bar(volume=10)])
    bars = [first] + follow(first, "gg", 1)
    calls = []
    def fetch(_client, sid, *args):
        calls.append(sid)
        return as_data(bars)
    monkeypatch.setattr(engine, "_intraday_with_retry", fetch)
    clock[0] = clock[0].replace(hour=9, minute=17, second=2)
    assert engine.evaluate_retest_breaks() == 0  # 09:17 breaking candle has not closed.
    assert calls == ["1"]
    engine.evaluate_retest_breaks()
    assert calls == ["1"]
    clock[0] += timedelta(minutes=1)
    assert engine.evaluate_retest_breaks() == 1
    assert calls == ["1", "1"]
    clock[0] += timedelta(minutes=1)
    engine.evaluate_retest_breaks()
    assert calls == ["1", "1"]  # Terminal setups no longer consume history requests.
    assert state.retest_break


def test_worker_stop_during_request_cannot_publish(engine, monkeypatch, clock):
    first = first_bar()
    state = seed(engine, first)
    stop = threading.Event()
    def fetch(*_):
        stop.set()
        return as_data([first] + follow(first, "g", 0))
    monkeypatch.setattr(engine, "_intraday_with_retry", fetch)
    clock[0] = clock[0].replace(hour=9, minute=17, second=2)
    engine.evaluate_retest_breaks(stop)
    assert not state.retest_break


def test_today_backtest_does_not_confirm_forming_breaking_candle(engine, clock):
    first = first_bar()
    state = seed(engine, first)
    history = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)]
    bars = [first] + follow(first, "g", 0)
    clock[0] = clock[0].replace(hour=9, minute=16, second=30)
    assert not engine._build_backtest_row(state.instrument, SESSION, history + bars, state.daily_filter)["retest_break"]
    clock[0] = clock[0].replace(minute=17)
    assert engine._build_backtest_row(state.instrument, SESSION, history + bars, state.daily_filter)["retest_break"]


def test_worker_fills_missing_open_cross_history_for_retest_without_gating_redwala(engine, monkeypatch, clock):
    first = first_bar()
    first.high = first.open  # This stock can have both badges.
    state = seed(engine, first)
    state.daily_filter.pop("five_day_closes")
    state.daily_filter.pop("five_day_highest_close")
    engine.update_volume_filters(VolumeFilterSettings(today_open_cross=True))
    assert state.redwala_gira
    assert state.retest_status == "unresolved"
    calls = []
    def daily(*_):
        calls.append("daily")
        return calculate_daily_filter(close_history(), SESSION)
    monkeypatch.setattr(engine, "_fetch_daily_filter", daily)
    monkeypatch.setattr(engine, "_intraday_with_retry", lambda *_: as_data([first] + follow(first, "g", 0)))
    clock[0] = clock[0].replace(hour=9, minute=17, second=2)
    assert engine.evaluate_retest_breaks() == 1
    assert state.redwala_gira and state.retest_break
    assert calls == ["daily"]
