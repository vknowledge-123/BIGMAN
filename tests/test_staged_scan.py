from datetime import datetime, timedelta
import threading

import pytest

from app.daily_filter import calculate_daily_filter
from app.dhan_scanner import Candle, Instrument, ScannerEngine, StockState
from app.storage import ConfigStore
from test_daily_filter import IST, SESSION, daily_data


@pytest.fixture
def clock(monkeypatch):
    now = [datetime(2026, 10, 1, 9, 10, tzinfo=IST)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now[0]

    monkeypatch.setattr("app.dhan_scanner.datetime", Clock)
    return now


def daily(passes=True):
    result = calculate_daily_filter(daily_data(), SESSION)
    result["passes"] = passes
    return result


def samples():
    return [{"date": day, "volume": 100_000, "candle_start": "09:15"}
            for day in ("2026-09-30", "2026-09-28", "2026-09-25")]


def prepared(symbol, sid="1"):
    return StockState(Instrument(symbol, sid, symbol), daily_filter=daily(),
                      opening_volume_average=100_000, opening_volume_samples=samples(),
                      volume_session=SESSION, preparation_status="ready")


@pytest.fixture
def engine(tmp_path, monkeypatch, clock):
    scanner = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    monkeypatch.setattr(scanner, "_client", lambda: object())
    monkeypatch.setattr(scanner, "refresh_circuit_limits", lambda *_: None)
    return scanner


def test_daily_first_only_survivors_need_minute_history_and_same_day_cache_reused(engine, monkeypatch):
    calls = []
    engine._states = {name: StockState(Instrument(name, str(i), name)) for i, name in enumerate(("A", "B", "C"))}

    def fetch_daily(_client, instrument, session):
        calls.append(("daily", instrument.symbol))
        return daily(instrument.symbol != "B")

    def fetch_volume(_client, instrument):
        calls.append(("volume", instrument.symbol))
        return samples(), []

    monkeypatch.setattr(engine, "_fetch_daily_filter", fetch_daily)
    monkeypatch.setattr(engine, "_fetch_opening_volume_history", fetch_volume)
    assert engine.cache_opening_volume_averages() == {"A": 100_000, "C": 100_000}
    assert calls == [("daily", "A"), ("daily", "B"), ("daily", "C"), ("volume", "A"), ("volume", "C")]
    persisted = engine.store.load()
    assert persisted.previous_closes == {"A": 102, "B": 102, "C": 102}
    assert persisted.opening_volume_cache["B"]["daily_filter"]["previous_high"] == 103
    assert engine._states["B"].preparation_status == "excluded"
    calls.clear()
    engine.cache_opening_volume_averages()
    assert calls == []
    engine._states["D"] = StockState(Instrument("D", "4", "D"))
    engine.cache_opening_volume_averages()
    assert calls == [("daily", "D"), ("volume", "D")]


def test_preparation_retries_missing_data_without_excluding_stock(engine, monkeypatch):
    engine._states = {"A": StockState(Instrument("A", "1", "A"))}
    count = [0]

    def fetch(*_):
        count[0] += 1
        if count[0] < 3:
            raise RuntimeError("Daily history missing")
        return daily()

    monkeypatch.setattr(engine, "_fetch_daily_filter", fetch)
    monkeypatch.setattr(engine, "_fetch_opening_volume_history", lambda *_: (samples(), []))
    assert engine.cache_opening_volume_averages() == {"A": 100_000}
    assert count == [3]
    assert engine._states["A"].error is None


def test_persistent_preparation_failure_remains_unresolved(engine, monkeypatch):
    state = StockState(Instrument("A", "1", "A"))
    engine._states = {"A": state}
    calls = []

    def fetch(*_):
        calls.append(1)
        raise RuntimeError("No daily bars")

    monkeypatch.setattr(engine, "_fetch_daily_filter", fetch)
    monkeypatch.setattr(engine, "_fetch_opening_volume_history", lambda *_: pytest.fail("Must not fetch minute history"))
    assert engine.cache_opening_volume_averages() == {}
    assert len(calls) == 3
    assert state.preparation_status == "unresolved"
    assert state.confirmation_status != "daily_rejected"


def test_restart_reuses_today_cache_and_discards_previous_sessions(engine, monkeypatch):
    state = prepared("A")
    engine.store.update_symbols(["A"])
    engine.store.update_previous_closes({"A": 90})
    engine.store.update_opening_volume_cache({"A": engine._cache_entry(state)})
    monkeypatch.setattr(engine.resolver, "resolve", lambda symbols: ({"A": state.instrument}, []))
    engine.load_saved()
    assert engine._volume_ready(engine._states["A"], SESSION)
    assert engine._states["A"].previous_close == 102
    old = engine._cache_entry(state)
    old["volume_session"] = "2026-09-30"
    old["daily_filter"] = dict(daily(), session_date="2026-09-30")
    engine.store.update_opening_volume_cache({"A": old})
    engine._states = {}
    engine.prepare_symbols(["A"])
    assert engine._states["A"].opening_volume_average is None
    assert engine._states["A"].preparation_status == "unresolved"


def tick(engine, clock, label, volume, price=100):
    clock[0] = datetime.fromisoformat(f"2026-10-01T{label}+05:30")
    engine._on_message(None, {"type": "Quote Data", "security_id": "1", "LTP": price,
                              "volume": volume, "LTT": label})


def test_timer_publishes_provisional_match_without_next_trade_then_confirms(engine, monkeypatch, clock):
    state = prepared("A")
    engine._states = {"A": state}
    engine._connected = True
    tick(engine, clock, "09:14:59", 100)
    assert state.current_candle is None
    tick(engine, clock, "09:15:00", 200, 100)
    tick(engine, clock, "09:15:59", 500_100, 101)
    clock[0] = datetime(2026, 10, 1, 9, 16, tzinfo=IST)
    engine._screen_live_opening(SESSION)
    row = engine.snapshot()["stocks"][0]
    assert row["awaiting_confirmation"] is True
    assert row["provisional_setup"] == "Possible candidate"
    assert row["possible_candidate"] is False
    assert row["first_candle_turnover"] == 50_500_000
    confirmed = Candle(datetime(2026, 10, 1, 9, 15, tzinfo=IST), 100, 102, 99, 101, 510_000)
    monkeypatch.setattr(engine, "_fetch_opening_candles", lambda *_: [confirmed])
    assert engine.evaluate_opening_candidates(only_pending=True) == 1
    row = engine.snapshot()["stocks"][0]
    assert row["confirmation_status"] == "confirmed"
    assert row["awaiting_confirmation"] is False
    assert row["first_candle_turnover"] == 51_510_000
    tick(engine, clock, "09:16:01", 520_100, 102)
    assert engine.snapshot()["stocks"][0]["first_candle_turnover"] == 51_510_000


def test_safe_volume_reject_skips_rest_but_missing_feed_is_confirmed(engine, monkeypatch, clock):
    state = prepared("A")
    engine._states = {"A": state}
    engine._connected = True
    tick(engine, clock, "09:14:59", 100)
    tick(engine, clock, "09:15:00", 110)
    tick(engine, clock, "09:15:59", 300)
    tick(engine, clock, "09:16:00", 350)
    engine._screen_live_opening(SESSION)
    assert state.confirmation_status == "local_rejected"
    monkeypatch.setattr(engine, "_fetch_opening_candles", lambda *_: pytest.fail("Locally rejected stock should be skipped"))
    assert engine.evaluate_opening_candidates(only_pending=True) == 0
    engine._on_close(None)
    assert state.feed_incomplete
    state.confirmation_status = "pending"
    state.signal_session = None
    confirmed = Candle(datetime(2026, 10, 1, 9, 15, tzinfo=IST), 100, 102, 99, 101, 500_000)
    monkeypatch.setattr(engine, "_fetch_opening_candles", lambda *_: [confirmed])
    assert engine.evaluate_opening_candidates(only_pending=True) == 1


def test_incomplete_apparent_reject_and_unresolved_only_retry_after_matches(engine, monkeypatch, clock):
    clock[0] = datetime(2026, 10, 1, 9, 16, tzinfo=IST)
    missing, candidate = prepared("M", "2"), prepared("A")
    first = Candle(datetime(2026, 10, 1, 9, 15, tzinfo=IST), 100, 102, 100, 101, 500_000)
    candidate.current_candle = first
    missing.current_candle = Candle(first.start, 100, 100, 99, 99, 10)
    engine._states = {"M": missing, "A": candidate}
    calls = []

    def fetch(_client, instrument):
        calls.append(instrument.symbol)
        if instrument.symbol == "M" and calls.count("M") == 1:
            raise RuntimeError("Candle not ready")
        return [first]

    monkeypatch.setattr(engine, "_fetch_opening_candles", fetch)
    engine.evaluate_opening_candidates(only_pending=True)
    assert calls == ["A", "M"]
    assert missing.confirmation_status == "unresolved"
    engine.evaluate_opening_candidates(only_pending=True)
    assert calls == ["A", "M", "M"]


def test_priority_confirmation_blocks_background_history_until_released(engine):
    calls = []
    started, finished = threading.Event(), threading.Event()

    def background():
        started.set()
        engine._history_call(lambda: calls.append("background"))
        finished.set()

    with engine._priority_history():
        worker = threading.Thread(target=background)
        worker.start()
        assert started.wait(1)
        assert not finished.wait(0.03)
        engine._history_call(lambda: calls.append("confirmation"))
    worker.join(2)
    assert finished.is_set()
    assert calls == ["confirmation", "background"]


def test_priority_released_on_error(engine):
    with pytest.raises(RuntimeError):
        with engine._priority_history():
            raise RuntimeError("failed")
    assert engine._priority_workers == 0
    assert not engine._history_reserved()


def test_300_stock_universe_reduces_preparation_and_confirmation_requests(engine, monkeypatch, clock):
    engine._states = {str(i): StockState(Instrument(str(i), str(i), str(i))) for i in range(300)}
    daily_calls, volume_calls, confirmation_calls = [], [], []

    def fetch_daily(_client, instrument, session):
        daily_calls.append(instrument.symbol)
        return daily(int(instrument.symbol) < 120)

    def fetch_volume(_client, instrument):
        volume_calls.append(instrument.symbol)
        return samples(), []

    monkeypatch.setattr(engine, "_fetch_daily_filter", fetch_daily)
    monkeypatch.setattr(engine, "_fetch_opening_volume_history", fetch_volume)
    assert len(engine.cache_opening_volume_averages()) == 120
    assert len(daily_calls) == 300
    assert len(volume_calls) == 120
    opening = datetime(2026, 10, 1, 9, 15, tzinfo=IST)
    clock[0] = opening + timedelta(minutes=1, seconds=1)
    engine._connected = True
    for i in range(120):
        state = engine._states[str(i)]
        state.current_candle = Candle(opening, 100, 102, 100, 101, 500_000 if i < 10 else 100)
        state.feed_incomplete = False
        state.feed_baseline_session = SESSION
        state.feed_baseline_volume = 0
        state.opening_first_tick = opening
        state.opening_last_tick = opening + timedelta(seconds=59)
        state.opening_boundary_seen = True
        state.opening_boundary_volume = state.current_candle.volume + 100

    def confirm(_client, instrument):
        confirmation_calls.append(instrument.symbol)
        return [engine._states[instrument.symbol].current_candle]

    monkeypatch.setattr(engine, "_fetch_opening_candles", confirm)
    assert engine.evaluate_opening_candidates(only_pending=True) == 10
    assert confirmation_calls == [str(i) for i in range(10)] + [str(i) for i in range(120, 300)]
    # Stocks excluded by daily volume still need a candle for turnover-only Redwala.
    assert sum(state.confirmation_status == "local_rejected" for state in engine._states.values()) == 110


def test_start_subscribes_all_stocks_including_daily_failures_for_redwala(engine, monkeypatch):
    engine.store.update_credentials("fake", "fake")
    engine._states = {"A": prepared("A"), "B": prepared("B", "2"),
                      "C": StockState(Instrument("C", "3", "C"))}
    engine._states["B"].daily_filter = daily(False)
    subscriptions = []

    class Feed:
        NSE = "NSE_EQ"
        Quote = "Quote"

        def __init__(self, context, instruments, *args, **kwargs):
            subscriptions.extend(instruments)

        def start(self):
            return None

        def close_connection(self):
            pass

    class Thread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr("app.dhan_scanner.MarketFeed", Feed)
    monkeypatch.setattr("app.dhan_scanner.DhanContext", lambda *_: object())
    monkeypatch.setattr("app.dhan_scanner.threading.Thread", Thread)
    engine.start()
    assert {item[1] for item in subscriptions} == {"1", "2", "3"}
    engine.stop()
