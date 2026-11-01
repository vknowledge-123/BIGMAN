from datetime import datetime, timedelta
import threading

import pytest
from pydantic import ValidationError

from app.daily_filter import apply_daily_volume_limit, calculate_daily_filter
from app.dhan_scanner import Candle, Instrument, ScannerEngine, StockState
from app.schemas import VolumeFilterSettings
from app.storage import ConfigStore
from test_daily_filter import IST, SESSION, daily_data
from test_staged_scan import clock, engine, prepared


def first_candle(color="green", volume=350_000):
    return Candle(datetime(2026, 10, 1, 9, 15, tzinfo=IST),
                  99 if color == "green" else 101, 101, 98, 100, volume)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
@pytest.mark.parametrize("field", ["daily_volume_max", "minute_volume_min", "first_candle_turnover_min"])
def test_invalid_settings(field, value):
    with pytest.raises(ValidationError):
        VolumeFilterSettings(**{field: value})


def test_persistence_and_legacy_defaults(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.path.write_text('{"symbols": ["AAA"]}')
    assert store.load().volume_filters == VolumeFilterSettings()
    settings = VolumeFilterSettings(daily_volume_max=2.5, minute_volume_min=6.25, first_candle_turnover_min=12_500_000)
    store.update_volume_filters(settings)
    store.update_previous_closes({"AAA": 100})
    restarted = ScannerEngine(ConfigStore(store.path))
    assert restarted.volume_filters == settings
    assert restarted.snapshot()["volume_filters"] == settings.model_dump()
    assert store.load().symbols == ["AAA"]


@pytest.mark.parametrize("volume,close,passes,exception", [
    (2500, 102, True, False), (2501, 102, False, False),
    (2501, 101, True, True), (2501, 99, True, True),
])
def test_custom_daily_boundary_and_cache_recalculation(volume, close, passes, exception):
    cached = calculate_daily_filter(daily_data(volume, close), SESSION)
    updated = apply_daily_volume_limit(cached, 2.5)
    fetched = calculate_daily_filter(daily_data(volume, close), SESSION, 2.5)
    assert updated == fetched
    assert updated["passes"] is passes
    assert updated["price_exception"] is exception
    assert cached["volume_limit"] == 4  # No mutation of another run's inputs.


@pytest.mark.parametrize("color", ["green", "red"])
@pytest.mark.parametrize("day_max,minute_min,qualifies", [
    (4, 4, False), (4, 3.5, True), (4, 3.5001, False),
    (2.5, 3, False), (3, 3, True),
])
def test_custom_filters_match_live_and_backtest(engine, monkeypatch, color, day_max, minute_min, qualifies):
    qualifies = qualifies or color == "red"
    settings = VolumeFilterSettings(daily_volume_max=day_max, minute_volume_min=minute_min)
    engine.update_volume_filters(settings)
    state = prepared("AAA")
    state.daily_filter = calculate_daily_filter(daily_data(3000, 102), SESSION)
    engine._states = {"AAA": state}
    first = first_candle(color)
    engine._apply_opening_candidate("AAA", [first])
    live = engine.snapshot()["stocks"][0]
    history = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)]
    monkeypatch.setattr(engine, "_fetch_backtest_history", lambda *_: history + [first])
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: state.daily_filter)
    result = engine.backtest_date(SESSION)
    assert result["volume_filters"] == settings.model_dump()
    assert result["qualified_count"] == int(qualifies)
    assert live["required_opening_volume"] == minute_min * 100_000
    for row in (live, result["stocks"][0]):
        assert row["qualifies_scan"] is qualifies
        assert row["possible_candidate"] is (qualifies and color == "green")
        assert row["redwala_gira"] is (qualifies and color == "red")
        assert row["daily_filter"]["volume_limit"] == day_max


def test_saving_rechecks_confirmed_candle_and_reopens_rejected_stocks(engine):
    confirmed, local, excluded = prepared("A"), prepared("B"), prepared("C")
    excluded.daily_filter = calculate_daily_filter(daily_data(5000, 102), SESSION)
    excluded.confirmation_status = "daily_rejected"
    local.confirmation_status = "local_rejected"
    engine._states = {"A": confirmed, "B": local, "C": excluded}
    engine._apply_opening_candidate("A", [first_candle()])
    assert not confirmed.qualifies_scan
    engine.update_volume_filters(VolumeFilterSettings(daily_volume_max=5, minute_volume_min=3))
    assert confirmed.qualifies_scan
    assert confirmed.confirmation_status == "confirmed"
    assert local.confirmation_status == "pending"
    assert excluded.preparation_status == "ready"
    assert excluded.confirmation_status == "pending"
    assert engine._row(excluded)["required_opening_volume"] == 300_000
    engine.update_volume_filters(VolumeFilterSettings(minute_volume_min=6))
    assert not confirmed.qualifies_scan
    assert excluded.confirmation_status == "pending"


def test_settings_keep_active_feed_and_signal_background_workers(engine, monkeypatch):
    engine._states = {"A": prepared("A")}
    engine._running = True
    monkeypatch.setattr(engine, "start", lambda: pytest.fail("Settings must not restart the feed"))
    monkeypatch.setattr(engine, "stop", lambda: pytest.fail("Settings must not wait for close_connection"))
    settings = VolumeFilterSettings(minute_volume_min=2.5)
    assert "Live connection kept running" in engine.update_volume_filters(settings)
    assert engine._running
    assert engine._candidate_refresh.is_set()
    assert engine._subscription_refresh.is_set()


def test_slow_subscription_does_not_block_saves_or_snapshots_and_edits_coalesce(engine):
    entered, release, second_sent = threading.Event(), threading.Event(), threading.Event()
    calls = []

    class Feed:
        def subscribe_symbols(self, instruments):
            calls.append([item[1] for item in instruments])
            if len(calls) == 1:
                entered.set()
                assert release.wait(3)
            else:
                second_sent.set()

    a, b, c = prepared("A", "1"), prepared("B", "2"), prepared("C", "3")
    b.daily_filter = calculate_daily_filter(daily_data(5000, 102), SESSION)
    c.daily_filter = calculate_daily_filter(daily_data(6000, 102), SESSION)
    engine._states = {"A": a, "B": b, "C": c}
    engine._running = engine._connected = True
    engine._feed = feed = Feed()
    engine._subscribed_symbols = {"A"}
    a.feed_baseline_volume = 123
    stop, refresh = engine._candidate_stop, engine._subscription_refresh
    worker = threading.Thread(target=engine._refresh_filter_subscriptions, args=(feed, stop, refresh))
    worker.start()
    try:
        engine.update_volume_filters(VolumeFilterSettings(daily_volume_max=5))
        assert entered.wait(2)
        # The previous network call is deliberately still blocked here.
        engine.update_volume_filters(VolumeFilterSettings(daily_volume_max=7))
        engine.update_volume_filters(VolumeFilterSettings(daily_volume_max=6, minute_volume_min=2))
        snapshot = engine.snapshot()
        assert snapshot["running"] and snapshot["connected"]
        assert snapshot["volume_filters"]["daily_volume_max"] == 6
        assert a.feed_baseline_volume == 123
        release.set()
        # Both stocks are subscribed immediately for turnover-only Redwala.
        assert calls == [["2", "3"]]
    finally:
        release.set()
        stop.set()
        refresh.set()
        worker.join(3)
    assert not worker.is_alive()


def test_completed_confirmation_worker_wakes_for_settings_without_new_feed(engine, monkeypatch):
    completed = threading.Event()
    calls = []
    engine._running = True
    stop, refresh = engine._candidate_stop, engine._candidate_refresh

    def confirm(event):
        calls.append(engine.volume_filters.minute_volume_min)
        completed.set()
        if len(calls) == 2:
            event.set()

    monkeypatch.setattr(engine, "_run_opening_confirmation", confirm)
    worker = threading.Thread(target=engine._refresh_opening_candidates_when_ready, args=(stop, refresh))
    worker.start()
    try:
        assert completed.wait(2)
        engine.update_volume_filters(VolumeFilterSettings(minute_volume_min=2))
        worker.join(2)
        assert calls == [4, 2]
        assert engine._opening_finished
    finally:
        stop.set()
        refresh.set()
        worker.join(2)


def test_save_rechecks_300_stocks_without_network_or_bulk_cache_write(engine, monkeypatch):
    for index in range(300):
        name = f"A{index}"
        engine._states[name] = prepared(name, str(index))
        engine._apply_opening_candidate(name, [first_candle()])
    monkeypatch.setattr(engine, "_client", lambda: pytest.fail("No network in settings request"))
    monkeypatch.setattr(engine.store, "update_opening_volume_cache", lambda *_: pytest.fail("No bulk cache rewrite"))
    engine.update_volume_filters(VolumeFilterSettings(minute_volume_min=3))
    assert sum(state.qualifies_scan for state in engine._states.values()) == 300


def test_backtest_keeps_one_settings_snapshot_when_live_changes(engine, monkeypatch):
    state = prepared("A")
    engine._states = {"A": state}
    first = first_candle()
    history = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)]
    initial = VolumeFilterSettings(daily_volume_max=2, minute_volume_min=3)
    changed = VolumeFilterSettings(daily_volume_max=1, minute_volume_min=6, first_candle_turnover_min=50_000_000, today_open_cross=True)
    engine._volume_filters = initial

    def fetch(*_):
        engine._volume_filters = changed  # Another request saves during the download.
        return history + [first]

    monkeypatch.setattr(engine, "_fetch_backtest_history", fetch)
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: state.daily_filter)
    result = engine.backtest_date(SESSION)
    assert result["volume_filters"] == initial.model_dump()
    assert result["qualified_count"] == 1
    assert engine.volume_filters == changed


def test_restart_recalculates_older_cache_without_refetching(engine, monkeypatch):
    state = prepared("A")
    state.daily_filter = calculate_daily_filter(daily_data(5000, 102), SESSION)
    engine.store.update_opening_volume_cache({"A": engine._cache_entry(state)})
    engine.update_volume_filters(VolumeFilterSettings(daily_volume_max=5))
    monkeypatch.setattr(engine.resolver, "resolve", lambda _: ({"A": state.instrument}, []))
    engine.prepare_symbols(["A"])
    assert engine._states["A"].preparation_status == "ready"
    assert engine._states["A"].opening_volume_average == 100_000


def test_local_volume_rejection_uses_selected_minimum(engine, clock):
    clock[0] = clock[0].replace(hour=9, minute=16, second=1)
    engine._connected = True
    state = prepared("A")
    state.current_candle = first_candle(volume=350_000)
    state.feed_baseline_session = SESSION
    state.feed_incomplete = False
    state.opening_first_tick = state.current_candle.start
    state.opening_last_tick = state.current_candle.end - timedelta(seconds=1)
    state.opening_boundary_seen = True
    state.feed_baseline_volume = 100
    state.opening_boundary_volume = 350_100
    engine._states = {"A": state}
    engine._screen_live_opening(SESSION)
    assert state.confirmation_status == "local_rejected"
    engine.update_volume_filters(VolumeFilterSettings(minute_volume_min=3))
    engine._screen_live_opening(SESSION)
    assert state.confirmation_status == "awaiting_confirmation"


@pytest.mark.parametrize("color", ["green", "red"])
@pytest.mark.parametrize("threshold,qualifies", [(34_999_999, True), (35_000_000, False), (35_000_001, False)])
def test_custom_turnover_strict_boundary_in_live_preview_confirmation_and_backtest(engine, monkeypatch, clock, color, threshold, qualifies):
    settings = VolumeFilterSettings(minute_volume_min=3, first_candle_turnover_min=threshold)
    engine.update_volume_filters(settings)
    state = prepared("A")
    engine._states = {"A": state}
    first = first_candle(color)
    state.current_candle = first
    clock[0] = clock[0].replace(hour=9, minute=16, second=1)
    engine._screen_live_opening(SESSION)
    assert bool(state.provisional_setup) is qualifies
    engine._apply_opening_candidate("A", [first])
    assert state.qualifies_scan is qualifies
    history = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)]
    monkeypatch.setattr(engine, "_fetch_backtest_history", lambda *_: history + [first])
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: state.daily_filter)
    result = engine.backtest_date(SESSION)
    assert result["qualified_count"] == int(qualifies)
    assert result["volume_filters"]["first_candle_turnover_min"] == threshold
    assert result["stocks"][0]["possible_candidate"] is (qualifies and color == "green")
    assert result["stocks"][0]["redwala_gira"] is (qualifies and color == "red")
    # Changes re-evaluate the stored confirmed candle without new API calls.
    engine.update_volume_filters(VolumeFilterSettings(minute_volume_min=3, first_candle_turnover_min=40_000_000))
    assert not state.qualifies_scan
    engine.update_volume_filters(VolumeFilterSettings(minute_volume_min=3, first_candle_turnover_min=20_000_000))
    assert state.qualifies_scan


def test_existing_volume_settings_receive_default_turnover(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.path.write_text('{"volume_filters": {"daily_volume_max": 2.5, "minute_volume_min": 6}}')
    loaded = store.load().volume_filters
    assert loaded.daily_volume_max == 2.5
    assert loaded.minute_volume_min == 6
    assert loaded.first_candle_turnover_min == 30_000_000


def test_request_filter_snapshot_is_cleared_after_failed_backtest(engine, monkeypatch):
    live = VolumeFilterSettings(minute_volume_min=7)
    chosen = VolumeFilterSettings(minute_volume_min=3)
    engine._volume_filters = live
    def fail(*_):
        assert engine.volume_filters == chosen
        raise RuntimeError('test download failure')
    monkeypatch.setattr(engine, '_backtest_date', fail)
    with pytest.raises(RuntimeError, match='test download failure'):
        engine.backtest_date(SESSION, volume_filters=chosen)
    assert engine.volume_filters == live
    assert not hasattr(engine._request_context, 'volume_filters')
