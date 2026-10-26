from datetime import timedelta

import pytest

from app.dhan_scanner import Candle
from app.schemas import VolumeFilterSettings
from app.setup_price_filters import evaluate, missing_history
from app.storage import ConfigStore
from test_staged_scan import SESSION, clock, engine, prepared
from test_open_cross import opening


def levels():
    return {**prepared("A").daily_filter, "previous_close": 100,
            "previous_high": 104, "previous_low": 100}


@pytest.mark.parametrize("op,cl,expected", [(101, 99, True), (101.001, 99, False),
    (100, 99, False), (99, 98, False), (101, 100, False), (101, 100.5, False),
    (100.25, 99.99, True)])
def test_redwala_gap_and_strict_cross(op, cl, expected):
    settings = VolumeFilterSettings(redwala_open_previous_close=True)
    result = evaluate(levels(), SESSION, op, cl, settings, "redwala")
    assert result["resolved"] and result["passes"] is expected


@pytest.mark.parametrize("high,limit,expected", [(104, 4, True), (104.001, 4, False),
    (103.75, 3.75, True), (100, 0, True), (104, 3.99, False)])
def test_pdhl_boundary(high, limit, expected):
    daily = {**levels(), "previous_high": high}
    result = evaluate(daily, SESSION, 101, 102, VolumeFilterSettings(pdhl_filter=True, pdhl_max=limit), "possible")
    assert result["passes"] is expected


@pytest.mark.parametrize("setup,field", [("possible", "pdhl_filter"), ("redwala", "redwala_open_previous_close")])
@pytest.mark.parametrize("corruption", ["none", "stale", "future", "zero", "nan", "missing", "inverted"])
def test_invalid_levels_unresolved_only_for_enabled_setup(setup, field, corruption):
    daily = levels()
    key = "previous_close" if setup == "redwala" else "previous_low"
    if corruption == "none": daily = None
    elif corruption == "stale": daily["session_date"] = "2026-09-30"
    elif corruption == "future": daily["previous_date"] = SESSION.isoformat()
    elif corruption == "missing": daily.pop(key)
    elif corruption == "inverted":
        daily[key] = -1 if setup == "redwala" else 105
    else: daily[key] = 0 if corruption == "zero" else float("nan")
    settings = VolumeFilterSettings(**{field: True})
    assert missing_history(daily, SESSION, settings, setup)
    assert evaluate(daily, SESSION, 101, 99, VolumeFilterSettings(), setup)["passes"]
    other = "possible" if setup == "redwala" else "redwala"
    assert evaluate(daily, SESSION, 101, 99, settings, other)["passes"]


@pytest.mark.parametrize("color,settings,expected", [
    ("red", {"redwala_open_previous_close": True}, True),
    ("red", {"redwala_open_previous_close": True, "redwala_open_gap_max": .99}, False),
    ("red", {"pdhl_filter": True, "pdhl_max": 0}, True),
    ("green", {"pdhl_filter": True}, True),
    ("green", {"pdhl_filter": True, "pdhl_max": 3.99}, False),
    ("green", {"redwala_open_previous_close": True, "redwala_open_gap_max": 0}, True),
])
def test_preview_confirmed_scanner_backtest_and_save_agree(engine, monkeypatch, clock, color, settings, expected):
    state = prepared("A")
    state.daily_filter = levels()
    engine._states = {"A": state}
    first = opening(101, color)
    if color == "red": first.close = first.low = 99
    state.current_candle = first
    filters = VolumeFilterSettings(**settings)
    engine.update_volume_filters(filters)
    clock[0] = clock[0].replace(hour=9, minute=16, second=1)
    engine._screen_live_opening(SESSION)
    assert bool(state.provisional_setup) is expected
    engine._apply_opening_candidate("A", [first])
    assert (state.redwala_gira if color == "red" else state.possible_candidate) is expected
    bars = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)] + [first]
    monkeypatch.setattr(engine, "_fetch_backtest_history", lambda *_: bars)
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: state.daily_filter)
    result = engine.backtest_date(SESSION)
    assert result["qualified_count"] == int(expected)
    assert result["volume_filters"] == filters.model_dump()
    monkeypatch.setattr(engine, "_client", lambda: pytest.fail("Saving must not fetch"))
    engine.update_volume_filters(VolumeFilterSettings())
    assert state.qualifies_scan
    engine.update_volume_filters(filters)
    assert state.qualifies_scan is expected
    assert ConfigStore(engine.store.path).load().volume_filters == filters


@pytest.mark.parametrize("color,field,key", [("green", "pdhl_filter", "previous_low"),
                                           ("red", "redwala_open_previous_close", "previous_close")])
def test_missing_levels_repair_reuses_candle_and_never_publishes_match(engine, monkeypatch, color, field, key):
    state = prepared("A")
    state.daily_filter = levels()
    state.daily_filter.pop(key)
    engine._states = {"A": state}
    engine.update_volume_filters(VolumeFilterSettings(**{field: True}))
    first = opening(101, color)
    if color == "red": first.close = first.low = 99
    engine._apply_opening_candidate("A", [first])
    assert not state.qualifies_scan and state.confirmation_status == "unresolved"
    assert not engine._opening_check_complete(state, SESSION)
    bars = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)] + [first]
    with pytest.raises(RuntimeError, match="needs valid previous"):
        engine._build_backtest_row(state.instrument, SESSION, bars, state.daily_filter)
    calls = []
    def fetch(*_):
        calls.append(1)
        return levels()
    monkeypatch.setattr(engine, "_fetch_daily_filter", fetch)
    monkeypatch.setattr(engine, "_fetch_opening_candles", lambda *_: pytest.fail("Reuse candle"))
    engine.evaluate_opening_candidates(only_pending=True)
    assert calls == [1]
    assert state.qualifies_scan and state.confirmation_status == "confirmed"


def test_retest_unaffected_by_both_new_filters(engine):
    state = prepared("A")
    state.daily_filter = levels()
    engine._states = {"A": state}
    engine.update_volume_filters(VolumeFilterSettings(pdhl_filter=True, pdhl_max=0,
        redwala_open_previous_close=True, redwala_open_gap_max=0))
    first = opening(101, "red")
    later = Candle(first.end, 100, 103, 100, 102, 100)
    engine._apply_opening_candidate("A", [first, later])
    assert not state.redwala_gira and not state.possible_candidate
    assert state.retest_break


def test_old_config_defaults_off(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.path.write_text('{"volume_filters": {"daily_volume_max": 3}}')
    assert not store.load().volume_filters.pdhl_filter
    assert not store.load().volume_filters.redwala_open_previous_close


def test_redwala_required_daily_auth_error_keeps_original_error_and_stops_batch(engine, monkeypatch):
    engine._states = {name: prepared(name) for name in ("A", "B")}
    engine.update_volume_filters(VolumeFilterSettings(redwala_open_previous_close=True))
    monkeypatch.setattr(engine, "_fetch_backtest_history", lambda *_: [opening(101, "red")])
    calls = []
    def fail(*_):
        calls.append(1)
        raise RuntimeError("Invalid_Authentication DH-901")
    monkeypatch.setattr(engine, "_fetch_daily_filter", fail)
    with pytest.raises(RuntimeError, match="DH-901"):
        engine.backtest_date(SESSION)
    assert calls == [1]
