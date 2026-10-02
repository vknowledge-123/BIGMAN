from datetime import date, datetime, timedelta
from itertools import product
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.daily_filter import calculate_daily_filter
from app.dhan_scanner import Candle, Instrument, ScannerEngine, StockState
from app.storage import ConfigStore


IST = ZoneInfo("Asia/Kolkata")
SESSION = date(2026, 10, 1)


def daily_data(volume=2000, close=102):
    # Gaps represent weekends and a missing trading session/holiday.
    days = [date(2026, 9, day) for day in (24, 25, 28, 30)]
    return {
        "timestamp": [datetime.combine(day, datetime.min.time(), tzinfo=IST).timestamp() for day in days],
        "close": [99, 100, 100, close],
        "volume": [500, 1000, 1500, volume],
    }


@pytest.mark.parametrize("volume,close,passes,exception", [
    (4000, 115, True, False),
    (4001, 101, True, True),
    (4001, 101.001, False, False),
    (5000, 99, True, True),
    (3000, 110, True, False),
])
def test_daily_boundaries(volume, close, passes, exception):
    result = calculate_daily_filter(daily_data(volume, close), SESSION)
    assert result["passes"] is passes
    assert result["price_exception"] is exception
    assert result["average"] == 1000
    assert result["multiplier"] == volume / 1000
    assert result["previous_date"] == "2026-09-30"
    assert [bar["date"] for bar in result["samples"]] == ["2026-09-24", "2026-09-25", "2026-09-28"]


def test_daily_ignores_target_and_future_and_sorts_returned_dates():
    data = daily_data()
    for offset in (0, 1):
        data["timestamp"].append(datetime(2026, 10, 1 + offset, tzinfo=IST).timestamp())
        data["close"].append(200)
        data["volume"].append(999999)
    reversed_data = {key: list(reversed(values)) for key, values in data.items()}
    assert calculate_daily_filter(reversed_data, SESSION) == calculate_daily_filter(daily_data(), SESSION)


@pytest.mark.parametrize("problem", ["missing", "mismatch", "zero", "nan", "negative", "duplicate"])
def test_invalid_daily_history_is_not_a_pass(problem):
    data = daily_data()
    if problem == "missing":
        data = {key: values[:3] for key, values in data.items()}
    elif problem == "mismatch":
        data["close"].pop()
    elif problem == "zero":
        data["volume"][:3] = [0, 0, 0]
    elif problem == "nan":
        data["close"][-1] = float("nan")
    elif problem == "negative":
        data["volume"][-1] = -1
    else:
        data["timestamp"].append(data["timestamp"][-1])
        data["close"].append(900)
        data["volume"].append(2000)
    with pytest.raises(ValueError):
        calculate_daily_filter(data, SESSION)


def pair(first_color, second_color, open_high=False, volume=400):
    close = {"green": 101, "red": 99, "doji": 100}
    candles = [
        Candle(datetime(2026, 10, 1, 9, 15, tzinfo=IST), 100,
               100 if open_high else 102, 98, close[first_color], volume),
    ]
    if second_color is not None:
        candles.append(Candle(datetime(2026, 10, 1, 9, 16, tzinfo=IST), 100, 102, 98, close[second_color], 200))
    return candles


PAIRS = [
    ("green", "green", False), ("green", "red", False),
    ("red", "green", False), ("red", "red", True),
    ("red", "red", False), ("doji", "green", False),
    ("green", "doji", False), ("doji", "doji", False),
    ("red", "green", True), ("red", "doji", True),
    ("red", None, True), ("red", None, False), ("green", None, False),
]


@pytest.mark.parametrize("colors,daily_mode,minute_volume", product(
    PAIRS, ["normal", "exception", "failed", "missing", "stale"], [399, 400, 401]
))
def test_live_and_backtest_share_all_qualification_rules(tmp_path, colors, daily_mode, minute_volume):
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    first, second, open_high = colors
    daily = calculate_daily_filter(daily_data(), SESSION)
    if daily_mode in {"exception", "failed"}:
        daily = calculate_daily_filter(daily_data(5000, 101 if daily_mode == "exception" else 102), SESSION)
    elif daily_mode == "missing":
        daily = None
    elif daily_mode == "stale":
        daily["session_date"] = "2026-09-30"
    instrument = Instrument("COALINDIA", "123", "COAL INDIA LTD")
    state = StockState(instrument, opening_volume_average=100, daily_filter=daily)
    engine._states = {"COALINDIA": state}
    candles = pair(first, second, open_high, minute_volume)
    engine._apply_opening_candidate("COALINDIA", candles)
    historical = [
        Candle(candles[0].start - timedelta(days=n), 100, 102, 98, 100, 100)
        for n in (1, 2, 3)
    ]
    backtest = engine._build_backtest_row(instrument, SESSION, historical + candles, daily)
    live = engine.snapshot()["stocks"][0]
    volume_pass = minute_volume >= 400 and daily_mode in {"normal", "exception"}
    candidate = volume_pass and (first, second) in {("green", "green"), ("green", "red"), ("red", "green")}
    redwala = volume_pass and first == "red" and open_high
    for row in (live, backtest):
        assert row["possible_candidate"] is candidate
        assert row["redwala_gira"] is redwala
        assert row["qualifies_scan"] is (candidate or redwala)
        assert row["is_fno"] is True
        assert row["volume_multiplier"] == minute_volume / 100
        assert row["first_candle_color"] == first
        assert row["second_candle_color"] == second


@pytest.fixture
def fixed_clock(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 1, 10, 0, tzinfo=IST).astimezone(tz)
    monkeypatch.setattr("app.dhan_scanner.datetime", FixedDatetime)
    monkeypatch.setattr("app.dhan_scanner.time.sleep", lambda _seconds: None)


class FakeDhan:
    def __init__(self, second_color="red"):
        self.daily_calls = []
        self.minute_calls = []
        self.fail_daily = False
        self.second_color = second_color
        self.quote_calls = []

    def quote_data(self, securities):
        self.quote_calls.append(securities)
        return {"status": "success", "data": {"NSE_EQ": {
            str(sid): {"upper_circuit_limit": 110, "lower_circuit_limit": 90, "last_price": 100}
            for sid in securities["NSE_EQ"]
        }}}

    def historical_daily_data(self, security_id, exchange, instrument_type, from_date, to_date):
        self.daily_calls.append((security_id, exchange, instrument_type, from_date, to_date))
        if self.fail_daily:
            return {"status": "failure", "remarks": {"error_code": "DH-901", "error_message": "Expired"}}
        return {"status": "success", "data": daily_data()}

    def intraday_minute_data(self, security_id, exchange, instrument_type, from_date, to_date, interval, oi):
        self.minute_calls.append((from_date, to_date, interval, oi))
        candles = pair("red", self.second_color, True)
        for day in (25, 28, 30):
            candles.append(Candle(datetime(2026, 9, day, 9, 15, tzinfo=IST), 100, 102, 99, 101, 100))
        data = {key: [getattr(candle, key) for candle in candles] for key in ("open", "high", "low", "close", "volume")}
        data["timestamp"] = [candle.start.timestamp() for candle in candles]
        return {"status": "success", "data": data}


@pytest.mark.parametrize("second_color", ["red", "green", "doji", None])
def test_sdk_cache_restart_repair_backtest_and_api_contract(tmp_path, monkeypatch, fixed_clock, second_color):
    import app.main as main

    store = ConfigStore(tmp_path / "config.json")
    store.update_symbols(["COALINDIA"])
    instrument = Instrument("COALINDIA", "123", "COAL INDIA LTD")
    engine = ScannerEngine(store)
    engine._states = {"COALINDIA": StockState(instrument)}
    client = FakeDhan(second_color)
    monkeypatch.setattr(engine, "_client", lambda: client)
    assert engine.cache_opening_volume_averages() == {"COALINDIA": 100}
    assert engine.snapshot()["stocks"][0]["redwala_gira"] is True
    assert len(client.quote_calls) == 1
    persisted = store.load().opening_volume_cache["COALINDIA"]["daily_filter"]
    assert persisted["previous_date"] == "2026-09-30"
    assert client.daily_calls[0][1:3] == ("NSE_EQ", "EQUITY")
    assert client.daily_calls[0][-1] == "2026-10-01"  # exclusive toDate

    restarted = ScannerEngine(store)
    monkeypatch.setattr(restarted.resolver, "resolve", lambda _symbols: ({"COALINDIA": instrument}, []))
    monkeypatch.setattr(restarted, "_client", lambda: client)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "scanner", restarted)
    with TestClient(main.app) as http:
        repair = http.post("/api/repair")
        assert repair.status_code == 200, repair.text
        assert len(client.daily_calls) == 1  # reuses today's persisted daily check
        live = http.get("/api/state").json()["stocks"][0]
        assert live["upper_circuit_distance_percent"] == 10
        quote_calls_before_backtest = len(client.quote_calls)
        backtest = http.post("/api/backtest", json={"target_date": SESSION.isoformat()})
        assert backtest.status_code == 200, backtest.text
        result = backtest.json()
        assert len(client.quote_calls) == quote_calls_before_backtest
        assert "upper_circuit_limit" not in result["stocks"][0]
        assert result["qualified_count"] == result["redwala_count"] == 1
        assert result["candidate_count"] == int(second_color == "green")
        for row in (live, result["stocks"][0]):
            assert row["redwala_gira"] is True
            assert row["qualifies_scan"] is True
            assert row["possible_candidate"] is (second_color == "green")
            assert row["second_candle_color"] == second_color
            assert row["first_open_equals_high"] is True
            assert row["daily_filter"] == persisted
        assert len(client.daily_calls) == 2
        assert all(call[2:] == (1, False) for call in client.minute_calls)
        assert store.load().opening_volume_cache["COALINDIA"]["daily_filter"] == persisted


def test_daily_auth_failure_clears_existing_badges_and_stops_batch(tmp_path, monkeypatch, fixed_clock):
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    client = FakeDhan()
    client.fail_daily = True
    monkeypatch.setattr(engine, "_client", lambda: client)
    engine._states = {
        symbol: StockState(Instrument(symbol, str(index), symbol), qualifies_scan=True, redwala_gira=True)
        for index, symbol in enumerate(("AAA", "BBB"))
    }
    with pytest.raises(RuntimeError, match="DH-901"):
        engine.cache_opening_volume_averages()
    assert len(client.daily_calls) == 1
    assert len(client.minute_calls) == 1
    assert all(not row["qualifies_scan"] and not row["redwala_gira"] for row in engine.snapshot()["stocks"])


def test_stale_daily_check_is_refetched_before_evaluation(tmp_path, monkeypatch, fixed_clock):
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    daily = calculate_daily_filter(daily_data(), SESSION)
    daily["session_date"] = "2026-09-30"
    state = StockState(Instrument("AAA", "123", "AAA"), opening_volume_average=100, daily_filter=daily)
    engine._states = {"AAA": state}
    client = FakeDhan()
    engine.evaluate_opening_candidates(client)
    assert len(client.daily_calls) == 1
    assert state.daily_filter["session_date"] == SESSION.isoformat()
    assert state.redwala_gira is True


@pytest.mark.parametrize("first_response_delayed", [False, True])
def test_live_refresh_checks_first_at_916_and_pair_at_917(tmp_path, monkeypatch, first_response_delayed):
    clock = [datetime(2026, 10, 1, 9, 15, 30, tzinfo=IST)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz)

    class StopEvent:
        def wait(self, seconds):
            clock[0] += timedelta(seconds=seconds)
            return False

    monkeypatch.setattr("app.dhan_scanner.datetime", Clock)
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    state = StockState(Instrument("AAA", "1", "AAA"), opening_volume_average=100,
                       daily_filter=calculate_daily_filter(daily_data(), SESSION))
    engine._states = {"AAA": state}
    monkeypatch.setattr(engine, "_client", lambda: object())
    calls = []

    def fetch(*_args):
        calls.append((clock[0].strftime("%H:%M"), state.redwala_gira))
        if clock[0].minute == 16:
            return [] if first_response_delayed else pair("red", None, True)
        return pair("red", "green", True)

    monkeypatch.setattr(engine, "_fetch_opening_candles", fetch)
    engine._refresh_opening_candidates_when_ready(StopEvent())
    assert calls == [("09:16", False), ("09:17", not first_response_delayed)]
    assert state.opening_pair_confirmed is True
    assert state.possible_candidate is True
    assert state.redwala_gira is True


def test_incomplete_first_candle_does_not_qualify(tmp_path, monkeypatch):
    class BeforeClose(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 1, 9, 15, 59, tzinfo=IST).astimezone(tz)

    monkeypatch.setattr("app.dhan_scanner.datetime", BeforeClose)
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    state = StockState(Instrument("AAA", "1", "AAA"), opening_volume_average=100,
                       daily_filter=calculate_daily_filter(daily_data(), SESSION))
    engine._states = {"AAA": state}
    with pytest.raises(RuntimeError, match="opening candle"):
        engine.evaluate_opening_candidates(FakeDhan())
    assert state.redwala_gira is False


def test_first_only_914_label_remains_supported(tmp_path):
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    state = StockState(Instrument("AAA", "1", "AAA"), opening_volume_average=100,
                       daily_filter=calculate_daily_filter(daily_data(), SESSION))
    engine._states = {"AAA": state}
    first = pair("red", None, True)[0]
    first.start -= timedelta(minutes=1)
    engine._apply_opening_candidate("AAA", [first])
    assert state.redwala_gira is True
    assert state.opening_pair_confirmed is False
