from datetime import datetime, timedelta
from itertools import product
import threading

import pytest

from app.daily_filter import calculate_daily_filter
from app.dhan_scanner import Candle
from app.opening_filters import evaluate, missing_history
from app.schemas import DailyVolumeFilter, VolumeFilterSettings
from app.storage import ConfigStore
from test_daily_filter import IST, SESSION
from test_open_cross import opening
from test_staged_scan import clock, engine, prepared


def history(colors=("green", "green")):
    days = []
    day = SESSION - timedelta(days=1)
    while len(days) < 21:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    days.reverse()
    closes = [9999, 210] + [190] * 17 + [198, 199]
    opens = [price - 1 for price in closes]
    for index, color in zip((-2, -1), colors):
        opens[index] = closes[index] + {"green": -1, "red": 1, "doji": 0}[color]
    return {"timestamp": [datetime.combine(day, datetime.min.time(), tzinfo=IST).timestamp() for day in days],
            "open": opens, "close": closes, "volume": [1000] * 21,
            "high": [price + 50 for price in closes], "low": [price - 50 for price in closes]}


def test_history_excludes_old_outlier_today_future_and_uses_trading_sessions():
    data = history(("red", "green"))
    expected = calculate_daily_filter(data, SESSION)
    for offset in (0, 1):
        data["timestamp"].append(datetime.combine(SESSION + timedelta(days=offset), datetime.min.time(), tzinfo=IST).timestamp())
        for field in ("open", "close", "volume", "high", "low"):
            data[field].append(999999)
    actual = calculate_daily_filter({key: list(reversed(values)) for key, values in data.items()}, SESSION)
    assert actual == expected
    parsed = DailyVolumeFilter.model_validate(actual)
    assert len(parsed.twenty_day_closes) == 20
    assert max(row["close"] for row in parsed.twenty_day_closes) == 210
    assert [row["open"] for row in parsed.last_two_day_candles] == [199, 198]


@pytest.mark.parametrize("colors", list(product(("green", "red", "doji"), repeat=2)))
@pytest.mark.parametrize("price", [198, 199, 200])
def test_two_day_color_and_strict_boundary_matrix(colors, price):
    daily = calculate_daily_filter(history(colors), SESSION)
    expected = colors == ("green", "green") or price > 199
    result = evaluate(daily, SESSION, price, VolumeFilterSettings(last_two_days_filter=True))
    assert result["resolved"]
    assert result["passes"] is expected


@pytest.mark.parametrize("monthly,two_days", list(product((False, True), repeat=2)))
@pytest.mark.parametrize("color", ["green", "red"])
@pytest.mark.parametrize("price", [199, 200, 210, 211])
def test_live_preview_confirmed_and_backtest_agree(engine, monkeypatch, clock, monthly, two_days, color, price):
    settings = VolumeFilterSettings(monthly_filter=monthly, last_two_days_filter=two_days)
    engine.update_volume_filters(settings)
    state = prepared("A")
    state.daily_filter = calculate_daily_filter(history(("red", "green")), SESSION)
    first = opening(price, color)
    state.current_candle = first
    engine._states = {"A": state}
    clock[0] = clock[0].replace(hour=9, minute=16, second=1)
    expected = color == "red" or ((not monthly or price > 210) and (not two_days or price > 199))
    engine._screen_live_opening(SESSION)
    assert bool(state.provisional_setup) is expected
    engine._apply_opening_candidate("A", [first])
    assert state.qualifies_scan is expected
    candles = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)] + [first]
    monkeypatch.setattr(engine, "_fetch_backtest_history", lambda *_: candles)
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: state.daily_filter)
    result = engine.backtest_date(SESSION)
    assert result["volume_filters"] == settings.model_dump()
    assert result["qualified_count"] == int(expected)
    assert result["stocks"][0]["possible_candidate"] is (expected and color == "green")
    assert result["stocks"][0]["redwala_gira"] is (expected and color == "red")




@pytest.mark.parametrize("field,key", [("monthly_filter", "twenty_day_closes"), ("last_two_days_filter", "last_two_day_candles")])
@pytest.mark.parametrize("corruption", ["missing", "short", "duplicate", "future", "stale", "nan"])
def test_missing_or_invalid_cache_never_passes(field, key, corruption):
    daily = calculate_daily_filter(history(), SESSION)
    if corruption == "missing":
        daily.pop(key)
    elif corruption == "short":
        daily[key].pop()
    elif corruption == "duplicate":
        daily[key][-1]["date"] = daily[key][-2]["date"]
    elif corruption == "future":
        daily[key][-1]["date"] = SESSION.isoformat()
    elif corruption == "stale":
        daily["session_date"] = (SESSION - timedelta(days=1)).isoformat()
    else:
        daily[key][-1]["close"] = float("nan")
    result = evaluate(daily, SESSION, 10000, VolumeFilterSettings(**{field: True}))
    assert not result["passes"] and not result["resolved"]
    assert evaluate(daily, SESSION, 10000, VolumeFilterSettings())["passes"]


@pytest.mark.parametrize("bad_open", [None, 0, -1, float("nan")])
def test_two_day_missing_open_is_unresolved(bad_open):
    data = history()
    data["open"][-1] = bad_open
    daily = calculate_daily_filter(data, SESSION)
    assert missing_history(daily, SESSION, VolumeFilterSettings(last_two_days_filter=True))


def test_legacy_cache_refresh_reuses_confirmed_candle(engine, monkeypatch):
    state = prepared("A")
    engine._states = {"A": state}
    engine._apply_opening_candidate("A", [opening(211, "green")])
    engine.update_volume_filters(VolumeFilterSettings(monthly_filter=True, last_two_days_filter=True))
    assert state.confirmation_status == "unresolved"
    assert not state.qualifies_scan
    calls = []
    def fetch(*_):
        calls.append(1)
        return calculate_daily_filter(history(("red", "green")), SESSION)
    monkeypatch.setattr(engine, "_fetch_daily_filter", fetch)
    monkeypatch.setattr(engine, "_fetch_opening_candles", lambda *_: pytest.fail("Must reuse confirmed candle"))
    engine.evaluate_opening_candidates(only_pending=True)
    assert state.possible_candidate and state.confirmation_status == "confirmed"
    engine.evaluate_opening_candidates(only_pending=True)
    assert calls == [1]
    assert len(engine.store.load().opening_volume_cache["A"]["daily_filter"]["twenty_day_closes"]) == 20


def test_settings_recheck_confirmed_results_without_network_and_persist(engine, monkeypatch):
    state = prepared("A")
    state.daily_filter = calculate_daily_filter(history(), SESSION)
    engine._states = {"A": state}
    engine._apply_opening_candidate("A", [opening(200)])
    assert state.possible_candidate
    monkeypatch.setattr(engine, "_client", lambda: pytest.fail("No network while saving"))
    settings = VolumeFilterSettings(monthly_filter=True, last_two_days_filter=True)
    engine.update_volume_filters(settings)
    assert not state.qualifies_scan
    assert ConfigStore(engine.store.path).load().volume_filters == settings
    engine.update_volume_filters(VolumeFilterSettings(last_two_days_filter=True))
    assert state.possible_candidate  # Both green bypasses only the new two-day check.


def test_short_optional_history_allows_shared_preparation_but_blocks_green_backtest(engine, monkeypatch):
    state = prepared("A")
    engine._states = {"A": state}
    engine.update_volume_filters(VolumeFilterSettings(monthly_filter=True))
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: state.daily_filter)
    monkeypatch.setattr(engine, "_fetch_opening_volume_history", lambda *_: pytest.fail("No minute fetch without daily history"))
    assert engine.cache_opening_volume_averages() == {"A": 100_000}
    assert state.preparation_status == "ready"
    first = opening(211)
    candles = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)] + [first]
    with pytest.raises(RuntimeError, match="20 completed"):
        engine._build_backtest_row(state.instrument, SESSION, candles, state.daily_filter)


@pytest.mark.parametrize("monthly,two_days", [(True, False), (False, True), (True, True)])
def test_redwala_never_requires_optional_history_live_backtest_or_settings_save(engine, monkeypatch, clock, monthly, two_days):
    state = prepared("A")  # No twenty-close history or valid daily opens.
    engine._states = {"A": state}
    first = opening(198, "red")
    state.current_candle = first
    engine._apply_opening_candidate("A", [first])
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: pytest.fail("Redwala must not fetch optional history"))
    engine.update_volume_filters(VolumeFilterSettings(monthly_filter=monthly, last_two_days_filter=two_days))
    assert state.redwala_gira and state.qualifies_scan
    assert state.confirmation_status == "confirmed" and state.error is None
    assert state.retest_status == "unresolved"  # Retest still requires the optional history.
    engine._prepare_daily(object(), state, SESSION)
    assert engine._opening_check_complete(state, SESSION)
    engine.evaluate_opening_candidates(only_pending=True)
    assert state.redwala_gira
    state.confirmation_status = "pending"
    clock[0] = clock[0].replace(hour=9, minute=16, second=1)
    engine._screen_live_opening(SESSION)
    assert state.provisional_setup == "redwala gira"
    candles = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)] + [first]
    row = engine._build_backtest_row(state.instrument, SESSION, candles, state.daily_filter)
    assert row["redwala_gira"] and row["qualifies_scan"]
    assert row["retest_status"] == "unresolved"


@pytest.mark.parametrize("price,expected", [(210, False), (211, True)])
def test_retest_obeys_new_filters(engine, price, expected):
    engine.update_volume_filters(VolumeFilterSettings(monthly_filter=True, last_two_days_filter=True))
    state = prepared("A")
    state.daily_filter = calculate_daily_filter(history(("red", "green")), SESSION)
    engine._states = {"A": state}
    first = opening(price, "red")
    later = Candle(first.start + timedelta(minutes=1), price - 1, price + 2, price - 1, price + 1, 100)
    engine._apply_opening_candidate("A", [first, later])
    assert state.retest_break is expected
    assert state.retest_status == ("confirmed" if expected else "filtered")




def test_old_settings_default_to_off(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.path.write_text('{"volume_filters": {"today_open_cross": true}}')
    assert not store.load().volume_filters.monthly_filter
    assert not store.load().volume_filters.last_two_days_filter
