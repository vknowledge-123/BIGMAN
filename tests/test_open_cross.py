from datetime import datetime, timedelta

import pytest

from app.daily_filter import calculate_daily_filter
from app.dhan_scanner import Candle
from app.schemas import DailyVolumeFilter, VolumeFilterSettings
from app.storage import ConfigStore
from test_daily_filter import IST, SESSION, daily_data
from test_staged_scan import clock, engine, prepared


def close_history():
    days = (21, 23, 24, 25, 28, 30)
    closes = [1000, 198, 199, 193, 192, 191]
    return {
        "timestamp": [datetime(2026, 9, day, tzinfo=IST).timestamp() for day in days],
        "close": closes, "volume": [1000] * 6,
        "high": [price + 50 for price in closes], "low": [price - 1 for price in closes],
    }


def opening(price=200, color="green"):
    close = price + (1 if color == "green" else -1)
    return Candle(datetime(2026, 10, 1, 9, 15, tzinfo=IST), price,
                  max(price, close), min(price, close), close, 500_000)


def test_five_trading_sessions_ignore_calendar_gaps_older_outlier_today_and_future():
    data = close_history()
    for day in (1, 2):
        data["timestamp"].append(datetime(2026, 10, day, tzinfo=IST).timestamp())
        for field in ("close", "high", "low", "volume"):
            data[field].append(9999)
    result = calculate_daily_filter({key: list(reversed(value)) for key, value in data.items()}, SESSION)
    assert result["five_day_highest_close"] == 199
    assert [item["close"] for item in result["five_day_closes"]] == [198, 199, 193, 192, 191]
    assert len({item["date"] for item in result["five_day_closes"]}) == 5
    assert DailyVolumeFilter.model_validate(result).five_day_highest_close == 199
    # All five highs are higher than 199; the condition uses CLOSE, never high.
    assert min(data["high"][:6]) > 199


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("color", ["green", "red"])
@pytest.mark.parametrize("price", [198, 199, 200])
def test_toggle_strict_open_boundary_matches_live_preview_confirmed_and_backtest(engine, monkeypatch, clock, enabled, color, price):
    settings = VolumeFilterSettings(today_open_cross=enabled)
    engine.update_volume_filters(settings)
    state = prepared("A")
    state.daily_filter = calculate_daily_filter(close_history(), SESSION)
    first = opening(price, color)
    state.current_candle = first
    engine._states = {"A": state}
    clock[0] = clock[0].replace(hour=9, minute=16, second=1)
    expected = color == "red" or not enabled or price > 199
    engine._screen_live_opening(SESSION)
    assert bool(state.provisional_setup) is expected
    engine._apply_opening_candidate("A", [first])
    assert state.qualifies_scan is expected
    history = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)]
    monkeypatch.setattr(engine, "_fetch_backtest_history", lambda *_: history + [first])
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: state.daily_filter)
    result = engine.backtest_date(SESSION)
    assert result["volume_filters"]["today_open_cross"] is enabled
    assert result["qualified_count"] == int(expected)
    assert result["stocks"][0]["possible_candidate"] is (expected and color == "green")
    assert result["stocks"][0]["redwala_gira"] is (expected and color == "red")
    if enabled and color == "green":
        assert f"highest close 199 ({'pass' if expected else 'fail'})" in state.candidate_reason


def test_changing_toggle_rechecks_existing_confirmed_results_without_network(engine, monkeypatch):
    state = prepared("A")
    state.daily_filter = calculate_daily_filter(close_history(), SESSION)
    engine._states = {"A": state}
    engine._apply_opening_candidate("A", [opening(199)])
    assert state.qualifies_scan
    monkeypatch.setattr(engine, "_client", lambda: pytest.fail("Save must not fetch history"))
    engine.update_volume_filters(VolumeFilterSettings(today_open_cross=True))
    assert not state.qualifies_scan
    assert state.confirmation_status == "confirmed"
    engine.update_volume_filters(VolumeFilterSettings(today_open_cross=False))
    assert state.qualifies_scan


def test_legacy_cache_upgrades_and_reuses_confirmed_first_candle(engine, monkeypatch):
    state = prepared("A")
    engine._states = {"A": state}
    engine._apply_opening_candidate("A", [opening()])
    engine.update_volume_filters(VolumeFilterSettings(today_open_cross=True))
    assert state.confirmation_status == "unresolved"
    assert not state.qualifies_scan
    assert not engine._opening_check_complete(state, SESSION)
    calls = []
    def fetch(*_):
        calls.append(1)
        return calculate_daily_filter(close_history(), SESSION)
    monkeypatch.setattr(engine, "_fetch_daily_filter", fetch)
    monkeypatch.setattr(engine, "_fetch_opening_candles", lambda *_: pytest.fail("Reuse the confirmed first candle"))
    engine.evaluate_opening_candidates(only_pending=True)
    assert calls == [1]
    assert state.qualifies_scan
    assert state.error is None
    assert engine.store.load().opening_volume_cache["A"]["daily_filter"]["five_day_highest_close"] == 199
    engine.evaluate_opening_candidates(only_pending=True)
    assert calls == [1]


def test_insufficient_history_is_unresolved_when_on_and_does_not_block_when_off(engine, monkeypatch):
    state = prepared("A")
    engine._states = {"A": state}
    engine.update_volume_filters(VolumeFilterSettings(today_open_cross=True))
    daily = calculate_daily_filter(daily_data(), SESSION)
    assert daily["five_day_highest_close"] is None
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: daily)
    engine._prepare_daily(object(), state, SESSION)
    assert engine._daily_ready(state, SESSION)  # Shared preparation must still allow Redwala.
    first = opening()
    candles = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)] + [first]
    with pytest.raises(RuntimeError, match="five completed"):
        engine._build_backtest_row(state.instrument, SESSION, candles, daily)
    engine.update_volume_filters(VolumeFilterSettings())
    assert engine._build_backtest_row(state.instrument, SESSION, candles, daily)["qualifies_scan"]


def test_redwala_unaffected_by_toggle_even_without_five_closes(engine, monkeypatch, clock):
    state = prepared("A")  # Four daily bars: enough for the original daily-volume filter.
    engine._states = {"A": state}
    first = opening(198, "red")
    state.current_candle = first
    clock[0] = clock[0].replace(hour=9, minute=16, second=1)
    engine._apply_opening_candidate("A", [first])
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: pytest.fail("Redwala needs no five-close refresh"))
    for enabled in (True, False, True):
        engine.update_volume_filters(VolumeFilterSettings(today_open_cross=enabled))
        assert state.redwala_gira
        assert state.confirmation_status == "confirmed"
        assert state.error is None
        assert "Today Open Cross unresolved" not in state.candidate_reason
        engine._prepare_daily(object(), state, SESSION)
        assert engine._opening_check_complete(state, SESSION)
    candles = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)] + [first]
    assert engine._build_backtest_row(state.instrument, SESSION, candles, state.daily_filter)["redwala_gira"]
    state.confirmation_status = "pending"
    engine._screen_live_opening(SESSION)
    assert state.provisional_setup == "redwala gira"


def test_toggle_persistence_default_and_old_settings_migration(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.path.write_text('{"volume_filters": {"daily_volume_max": 2, "minute_volume_min": 3}}')
    assert store.load().volume_filters.today_open_cross is False
    store.update_volume_filters(VolumeFilterSettings(today_open_cross=True))
    assert ConfigStore(store.path).load().volume_filters.today_open_cross is True
