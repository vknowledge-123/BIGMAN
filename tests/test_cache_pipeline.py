import json
import threading
import time
from datetime import datetime, date, timedelta

import pytest

from app.dhan_scanner import Candle, Instrument, ScannerEngine, StockState
from app.storage import ConfigStore
from test_daily_filter import IST, SESSION, daily_data
from test_staged_scan import clock, engine, daily, samples, prepared


def payload(candles):
    return {"timestamp": [b.start.timestamp() for b in candles],
            **{name: [getattr(b, name) for b in candles] for name in ("open", "high", "low", "close", "volume")}}


def candle(day, hour=9, minute=15, volume=100):
    return Candle(datetime.combine(day, datetime.min.time(), tzinfo=IST).replace(hour=hour, minute=minute),
                  100, 102, 99, 101, volume)


def test_legacy_migration_separates_settings_and_updates_only_one_stock(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    old = {"client_id": "test-client", "access_token": "test-token", "symbols": ["A", "B"],
           "opening_volume_cache": {s: {"daily_filter": daily(), "average": 123} for s in ("A", "B")},
           "previous_closes": {"A": 100, "B": 200}}
    path.write_text(json.dumps(old))
    store = ConfigStore(path)
    loaded = store.load()
    assert loaded.opening_volume_cache == old["opening_volume_cache"]
    settings = json.loads(path.read_text())
    assert settings == {k: v for k, v in old.items() if k not in ("opening_volume_cache", "previous_closes")}
    before = path.read_bytes()
    monkeypatch.setattr(store, "_save_settings", lambda *_: pytest.fail("History must not rewrite settings"))
    store.update_opening_volume_cache({"A": {"daily_filter": daily(), "average": 456}})
    assert path.read_bytes() == before
    assert store.load().opening_volume_cache["A"]["average"] == 456
    assert store.load().opening_volume_cache["B"]["average"] == 123
    assert ConfigStore(path).load().previous_closes == {"A": 100, "B": 200}


def test_failed_migration_is_retryable_and_does_not_overwrite_new_data(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"opening_volume_cache": {"A": {"average": 1}}}))
    store = ConfigStore(path)
    original = store._save_settings
    monkeypatch.setattr(store, "_save_settings", lambda *_: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        store.load()
    store.history.update({"A": {"average": 2}})
    monkeypatch.setattr(store, "_save_settings", original)
    assert store.load().opening_volume_cache["A"]["average"] == 2
    assert "opening_volume_cache" not in json.loads(path.read_text())


def test_concurrent_stores_keep_other_symbols_and_newer_snapshot(tmp_path):
    path = tmp_path / "config.json"
    stores = [ConfigStore(path) for _ in range(4)]
    errors = []
    def write(i):
        try:
            for j in range(20):
                stores[i].update_opening_volume_cache({f"S{i}-{j}": {"average": j}})
        except Exception as exc:
            errors.append(exc)
    workers = [threading.Thread(target=write, args=(i,)) for i in range(4)]
    for worker in workers: worker.start()
    for worker in workers: worker.join(5)
    assert not errors
    assert all(not w.is_alive() for w in workers)
    assert len(stores[0].load().opening_volume_cache) == 80
    stores[0].history.update({"A": {"cached_at": "2026-10-01T09:10:02", "average": 2}})
    stores[1].history.update({"A": {"cached_at": "2026-10-01T09:10:01", "average": 1}})
    assert stores[0].load().opening_volume_cache["A"]["average"] == 2


def test_266_stocks_publish_before_batch_flush_and_do_not_rewrite_config(engine, monkeypatch):
    engine._states = {str(i): StockState(Instrument(str(i), str(i), str(i))) for i in range(266)}
    writes = []
    update = engine.store.update_opening_volume_cache
    def persist(entries):
        writes.append(len(entries))
        update(entries)
    monkeypatch.setattr(engine.store, "update_opening_volume_cache", persist)
    monkeypatch.setattr(engine.store, "_save_settings", lambda *_: pytest.fail("No config rewrite"))
    def fetch_daily(client, instrument, session):
        if instrument.symbol == "1":
            assert engine._states["0"].preparation_status == "ready"
            assert engine._states["0"].opening_volume_average == 100_000
            assert writes == []  # Available to live work before persisted batch.
        return daily()
    monkeypatch.setattr(engine, "_fetch_daily_filter", fetch_daily)
    monkeypatch.setattr(engine, "_fetch_opening_volume_history", lambda *_: (samples(), []))
    assert len(engine.cache_opening_volume_averages()) == 266
    assert sum(writes) <= 280  # Flush boundaries may include the finishing stock again.
    assert len(writes) < 25
    assert len(engine.store.load().opening_volume_cache) == 266


def test_daily_rollover_fetches_delta_and_backtest_cannot_use_future(engine, monkeypatch):
    instrument = Instrument("A", "1", "A")
    calls = []
    responses = [daily_data(), {"timestamp": [datetime(2026, 10, 1, tzinfo=IST).timestamp()],
                 "open": [101], "high": [106], "low": [100], "close": [105], "volume": [3000]}]
    def fetch(*args):
        calls.append(args[-2:])
        return responses.pop(0)
    monkeypatch.setattr(engine, "_historical_daily_with_retry", fetch)
    first = engine._fetch_daily_filter(object(), instrument, SESSION)
    assert engine._fetch_daily_filter(object(), instrument, SESSION) == first
    tomorrow = engine._fetch_daily_filter(object(), instrument, SESSION + timedelta(days=1))
    assert calls[-1] == ("2026-09-30", "2026-10-02")
    assert tomorrow["previous_date"] == "2026-10-01"
    assert tomorrow["previous_close"] == 105
    # Earlier replay needs a larger earlier coverage window; it refetches, never uses Oct 1.
    responses.append(daily_data())
    earlier = engine._fetch_daily_filter(object(), instrument, SESSION)
    assert earlier["previous_date"] == "2026-09-30"
    assert engine.store.history.get("daily", engine._instrument_cache_key(instrument))["through"] == "2026-10-02"


@pytest.mark.parametrize("bad", [{"version": 1}, {"version": 1, "start": "2020-01-01", "through": "2026-10-01", "bars": [{"date": "bad"}]}])
def test_malformed_daily_cache_recovers(engine, monkeypatch, bad):
    instrument = Instrument("A", "1", "A")
    engine.store.history.put("daily", engine._instrument_cache_key(instrument), bad)
    calls = []
    monkeypatch.setattr(engine, "_historical_daily_with_retry", lambda *args: calls.append(args) or daily_data())
    assert engine._fetch_daily_filter(object(), instrument, SESSION)["previous_close"] == 102
    assert len(calls) == 1


def test_opening_samples_roll_forward_and_keep_previous_close_context(engine, monkeypatch, clock):
    instrument = Instrument("A", "1", "A")
    calls = []
    history = [candle(date(2026, 9, d)) for d in (24, 25, 28, 30)]
    history += [candle(date(2026, 9, d), 15, 29) for d in (24, 25, 28, 30)]
    responses = [payload(history), payload([candle(SESSION, volume=400), candle(SESSION, 15, 29)])]
    def fetch(*args):
        calls.append(args[-2:])
        return responses.pop(0)
    monkeypatch.setattr(engine, "_intraday_with_retry", fetch)
    initial, _ = engine._fetch_opening_volume_history(object(), instrument)
    assert [r["date"] for r in initial] == ["2026-09-30", "2026-09-28", "2026-09-25"]
    assert engine._fetch_opening_volume_history(object(), instrument)[0] == initial
    clock[0] += timedelta(days=1)
    updated, _ = engine._fetch_opening_volume_history(object(), instrument)
    assert calls[-1][0] == "2026-10-01 00:00:00"
    assert [r["date"] for r in updated] == ["2026-10-01", "2026-09-30", "2026-09-28"]
    assert updated[0]["volume"] == 400
    assert len(calls) == 2


def test_missing_opening_recovery_logs_timestamps_and_uses_wide_only_on_retry(engine, monkeypatch, clock):
    clock[0] = datetime(2026, 10, 1, 9, 22, tzinfo=IST)
    instrument = Instrument("A", "1", "A")
    calls = []
    def fetch(*args):
        calls.append(args[-2:])
        return payload([candle(SESSION, minute=16)])
    monkeypatch.setattr(engine, "_intraday_with_retry", fetch)
    with pytest.raises(RuntimeError, match="returned 1 candles"):
        engine._fetch_opening_candles(object(), instrument)
    assert len(calls) == 2
    assert calls[0][0] == "2026-10-01 09:14:00"
    assert calls[1][0] == "2026-09-30 00:00:00"
    diagnostic = engine.store.history.get("opening_diagnostic", engine._instrument_cache_key(instrument))
    assert diagnostic["first_timestamp"] == "2026-10-01T09:16:00+05:30"
    assert diagnostic["opening_found"] is False
    with pytest.raises(RuntimeError): engine._fetch_opening_candles(object(), instrument)
    assert len(calls) == 3
    monkeypatch.setattr(engine, "_intraday_with_retry", lambda *_: payload([candle(SESSION)]))
    assert engine._fetch_opening_candles(object(), instrument)[0].start.minute == 15
    assert engine._opening_diagnostics["A"]["opening_found"] is True


def test_confirmation_skips_busy_preparation_without_duplicate_requests(engine, monkeypatch, clock):
    clock[0] = datetime(2026, 10, 1, 9, 16, tzinfo=IST)
    engine._states = {"A": prepared("A"), "B": prepared("B", "2")}
    held, release = threading.Event(), threading.Event()
    def prepare():
        with engine._work_lock("A"):
            held.set()
            release.wait(3)
    worker = threading.Thread(target=prepare)
    worker.start()
    assert held.wait(2)
    calls = []
    monkeypatch.setattr(engine, "_fetch_opening_candles", lambda _, i: calls.append(i.symbol) or [candle(SESSION, volume=500_000)])
    try:
        engine.evaluate_opening_candidates(only_pending=True)
        assert calls == ["B"]
    finally:
        release.set(); worker.join(2)
    engine.evaluate_opening_candidates(only_pending=True)
    assert calls == ["B", "A"]


def test_confirmation_keeps_retrying_after_six_passes(engine, monkeypatch, clock):
    clock[0] = datetime(2026, 10, 1, 9, 16, tzinfo=IST)
    engine._states = {"A": prepared("A")}
    monkeypatch.setattr("app.dhan_scanner.time.monotonic", lambda: clock[0].timestamp())
    calls = []
    def fetch(*_):
        calls.append(1)
        if len(calls) < 8: raise RuntimeError("not ready")
        return [candle(SESSION, volume=500_000)]
    class Stop:
        def is_set(self): return False
        def wait(self, seconds):
            clock[0] += timedelta(seconds=seconds)
            return False
    monkeypatch.setattr(engine, "_fetch_opening_candles", fetch)
    engine._run_opening_confirmation(Stop())
    assert len(calls) == 8
    assert engine._states["A"].confirmation_status == "confirmed"


def test_scheduler_reserves_every_fourth_waiting_slot_for_background(engine, monkeypatch):
    monkeypatch.setattr("app.dhan_scanner.HISTORY_REQUEST_SPACING", 0)
    calls, errors = [], []
    def request(priority, label):
        try:
            engine._request_context.priority = priority
            engine._history_call(lambda: calls.append(label))
        except Exception as exc: errors.append(exc)
    engine._history_busy = True
    workers = [threading.Thread(target=request, args=(i < 7, f"p{i}" if i < 7 else "background")) for i in range(8)]
    for worker in workers: worker.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with engine._history_condition:
            if len(engine._history_waiters) == 8: break
        time.sleep(.005)
    with engine._history_condition:
        assert len(engine._history_waiters) == 8
        engine._history_busy = False
        engine._history_condition.notify_all()
    for worker in workers: worker.join(2)
    assert not errors
    assert all(not w.is_alive() for w in workers)
    assert calls[3] == "background"
    assert len(calls) == 8


@pytest.mark.parametrize("delta", ["empty", "overlap_only"])
def test_empty_or_stale_daily_delta_requires_full_recheck(engine, monkeypatch, delta):
    instrument = Instrument("A", "1", "A")
    monkeypatch.setattr(engine, "_historical_daily_with_retry", lambda *_: daily_data())
    engine._fetch_daily_filter(object(), instrument, SESSION)
    responses = [({} if delta == "empty" else daily_data()), daily_data()]
    calls = []
    def fetch(*args):
        calls.append(args[-2:])
        return responses.pop(0)
    monkeypatch.setattr(engine, "_historical_daily_with_retry", fetch)
    result = engine._fetch_daily_filter(object(), instrument, SESSION + timedelta(days=1))
    assert len(calls) == 2
    assert calls[0][0] == "2026-09-30"
    assert calls[1][0] < calls[0][0]
    assert result["previous_date"] == "2026-09-30"  # e.g. a holiday; never invent a daily candle.


@pytest.mark.parametrize("coverage", ["2026-08-01", "2026-10-02", "bad"])
def test_old_future_or_malformed_opening_cache_cannot_supply_samples(engine, monkeypatch, coverage):
    instrument = Instrument("A", "1", "A")
    rows = [dict(start=candle(date(2026, 9, d)).start.isoformat(), open=100, high=102, low=99, close=101, volume=99999)
            for d in (24, 25, 28)]
    engine.store.history.put("opening", engine._instrument_cache_key(instrument), {"version":1, "through":coverage, "bars":rows})
    calls = []
    fresh = [candle(date(2026, 9, d), volume=10) for d in (25, 28, 30)]
    monkeypatch.setattr(engine, "_intraday_with_retry", lambda *args: calls.append(args) or payload(fresh))
    result, _ = engine._fetch_opening_volume_history(object(), instrument)
    assert len(calls) == 1
    assert all(row["volume"] == 10 for row in result)


def test_empty_opening_delta_refetches_full_window(engine, monkeypatch, clock):
    instrument = Instrument("A", "1", "A")
    bars = [candle(date(2026, 9, d)) for d in (25, 28, 30)]
    monkeypatch.setattr(engine, "_intraday_with_retry", lambda *_: payload(bars))
    engine._fetch_opening_volume_history(object(), instrument)
    clock[0] += timedelta(days=1)
    calls = []
    responses = [payload([]), payload(bars + [candle(SESSION, volume=600)])]
    def fetch(*args):
        calls.append(args[-2:])
        return responses.pop(0)
    monkeypatch.setattr(engine, "_intraday_with_retry", fetch)
    result, _ = engine._fetch_opening_volume_history(object(), instrument)
    assert len(calls) == 2
    assert result[0]["date"] == "2026-10-01"
    assert result[0]["volume"] == 600
