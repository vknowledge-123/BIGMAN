from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.dhan_scanner import Candle, Instrument, InstrumentResolver, ScannerEngine, StockState, parse_symbols
from app.storage import ConfigStore


IST = ZoneInfo("Asia/Kolkata")


def test_parse_symbols_deduplicates_and_accepts_commas() -> None:
    assert parse_symbols(" coalindia\nOIL, oil\tTBZ ") == ["COALINDIA", "OIL", "TBZ"]


def test_completed_candle_turnover_uses_candle_close() -> None:
    candle = Candle(
        start=datetime(2026, 9, 2, 9, 33, tzinfo=IST),
        open=100,
        high=104,
        low=99,
        close=102,
        volume=2500,
    )
    assert candle.turnover == 255000


def test_snapshot_sorts_by_percent_change_then_turnover(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    engine = ScannerEngine(store)
    first = StockState(Instrument("AAA", "1", "AAA LTD"), previous_close=100, ltp=110, percent_change=10)
    second = StockState(Instrument("BBB", "2", "BBB LTD"), previous_close=100, ltp=109, percent_change=9)
    third = StockState(Instrument("CCC", "3", "CCC LTD"), previous_close=100, ltp=110, percent_change=10)
    first.completed_candle = Candle(datetime(2026, 9, 2, 9, 33, tzinfo=IST), 10, 10, 10, 10, 100)
    second.completed_candle = Candle(datetime(2026, 9, 2, 9, 33, tzinfo=IST), 10, 10, 10, 10, 100000)
    third.completed_candle = Candle(datetime(2026, 9, 2, 9, 33, tzinfo=IST), 10, 10, 10, 10, 200)

    with engine._lock:
        engine._states = {"AAA": first, "BBB": second, "CCC": third}

    assert [row["symbol"] for row in engine.snapshot()["stocks"]] == ["CCC", "AAA", "BBB"]


def test_instrument_resolver_selects_nse_equity(tmp_path) -> None:
    csv_path = tmp_path / "master.csv"
    csv_path.write_text(
        "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_TRADING_SYMBOL,SEM_SERIES,SM_SYMBOL_NAME\n"
        "BSE,E,999,EQUITY,COALINDIA,EQ,WRONG EXCHANGE\n"
        "NSE,E,20374,EQUITY,COALINDIA,EQ,COAL INDIA LTD\n"
        "NSE,D,1,FUTCUR,USDINR,NA,USDINR\n",
        encoding="utf-8",
    )
    resolver = InstrumentResolver(csv_path)

    resolved, unresolved = resolver.resolve(["COALINDIA", "MISSING"])

    assert unresolved == ["MISSING"]
    assert resolved["COALINDIA"].security_id == "20374"
    assert resolved["COALINDIA"].exchange_segment == "NSE_EQ"


def test_cache_previous_closes_updates_state_and_store(tmp_path) -> None:
    class FakeClient:
        def ohlc_data(self, *_args, **_kwargs):
            return {"status": "success", "data": {"NSE_EQ": {}}}

        def historical_daily_data(self, *_args, **_kwargs):
            return {"status": "success", "data": {"close": [98.5, 101.25]}}

    store = ConfigStore(tmp_path / "config.json")
    store.update_credentials("client", "token")
    engine = ScannerEngine(store)
    engine._client = lambda: FakeClient()  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {
            "AAA": StockState(Instrument("AAA", "123", "AAA LTD"), opening_volume_average=200)
        }

    cached = engine.cache_previous_closes()

    assert cached == {"AAA": 101.25}
    assert store.load().previous_closes == {"AAA": 101.25}


def test_cache_previous_closes_uses_single_ohlc_batch_when_available(tmp_path) -> None:
    class FakeClient:
        ohlc_calls = 0
        historical_calls = 0

        def ohlc_data(self, securities):
            self.ohlc_calls += 1
            assert securities == {"NSE_EQ": [123, 456]}
            return {
                "status": "success",
                "data": {
                    "NSE_EQ": {
                        "123": {"last_price": 110, "ohlc": {"close": 100}},
                        "456": {"last_price": 190, "ohlc": {"close": 200}},
                    }
                },
            }

        def historical_daily_data(self, *_args, **_kwargs):
            self.historical_calls += 1
            raise AssertionError("Historical fallback should not be called")

    store = ConfigStore(tmp_path / "config.json")
    store.update_credentials("client", "token")
    client = FakeClient()
    engine = ScannerEngine(store)
    engine._client = lambda: client  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {
            "AAA": StockState(Instrument("AAA", "123", "AAA LTD")),
            "BBB": StockState(Instrument("BBB", "456", "BBB LTD")),
        }

    cached = engine.cache_previous_closes()
    snapshot = engine.snapshot()["stocks"]

    assert client.ohlc_calls == 1
    assert client.historical_calls == 0
    assert cached == {"AAA": 100, "BBB": 200}
    assert {row["symbol"]: row["percent_change"] for row in snapshot} == {"AAA": 10, "BBB": -5}


def test_cache_rate_limit_does_not_fan_out_to_historical_calls(tmp_path) -> None:
    class FakeClient:
        historical_calls = 0

        def ohlc_data(self, *_args, **_kwargs):
            return {
                "status": "failure",
                "remarks": {
                    "error_code": "DH-904",
                    "error_type": "Rate_Limit",
                    "error_message": "Too many requests",
                },
            }

        def historical_daily_data(self, *_args, **_kwargs):
            self.historical_calls += 1
            return {"status": "success", "data": {"close": [100]}}

    store = ConfigStore(tmp_path / "config.json")
    store.update_credentials("client", "token")
    client = FakeClient()
    engine = ScannerEngine(store)
    engine._client = lambda: client  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {"AAA": StockState(Instrument("AAA", "123", "AAA LTD"))}

    assert engine.cache_previous_closes() == {}
    assert client.historical_calls == 0
    assert engine.snapshot()["stocks"][0]["status"] == "rate limited"


def test_opening_candidate_badge_green_red(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    engine = ScannerEngine(store)
    engine._client = lambda: object()  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {
            "AAA": StockState(Instrument("AAA", "123", "AAA LTD"), opening_volume_average=200)
        }

    first = Candle(datetime(2026, 9, 2, 9, 15, tzinfo=IST), 100, 105, 99, 104, 1000)
    second = Candle(datetime(2026, 9, 2, 9, 16, tzinfo=IST), 104, 105, 101, 102, 1200)
    engine._fetch_opening_candles = lambda *_args, **_kwargs: [first, second]  # type: ignore[method-assign]

    assert engine.evaluate_opening_candidates() == 1
    row = engine.snapshot()["stocks"][0]
    assert row["possible_candidate"] is True
    assert row["volume_multiplier"] == 5
    assert "Matched 09:15/09:16: 09:15 green, 09:16 red" in row["candidate_reason"]


def test_opening_candidate_badge_red_green(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    engine = ScannerEngine(store)
    engine._client = lambda: object()  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {
            "AAA": StockState(Instrument("AAA", "123", "AAA LTD"), opening_volume_average=200)
        }

    first = Candle(datetime(2026, 9, 2, 9, 15, tzinfo=IST), 100, 101, 96, 98, 1000)
    second = Candle(datetime(2026, 9, 2, 9, 16, tzinfo=IST), 98, 102, 97, 101, 1200)
    engine._fetch_opening_candles = lambda *_args, **_kwargs: [first, second]  # type: ignore[method-assign]

    assert engine.evaluate_opening_candidates() == 1
    assert engine.snapshot()["stocks"][0]["possible_candidate"] is True


def test_opening_candidate_badge_rejects_red_red(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    engine = ScannerEngine(store)
    engine._client = lambda: object()  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {
            "AAA": StockState(Instrument("AAA", "123", "AAA LTD"), opening_volume_average=200)
        }

    first = Candle(datetime(2026, 9, 2, 9, 15, tzinfo=IST), 100, 101, 96, 98, 1000)
    second = Candle(datetime(2026, 9, 2, 9, 16, tzinfo=IST), 98, 99, 94, 95, 1200)
    engine._fetch_opening_candles = lambda *_args, **_kwargs: [first, second]  # type: ignore[method-assign]

    assert engine.evaluate_opening_candidates() == 0
    row = engine.snapshot()["stocks"][0]
    assert row["possible_candidate"] is False
    assert "09:15/09:16: 09:15 red, 09:16 red" in row["candidate_reason"]


def test_opening_candidate_badge_requires_opposite_colors(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    engine = ScannerEngine(store)
    engine._client = lambda: object()  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {
            "AAA": StockState(Instrument("AAA", "123", "AAA LTD"), opening_volume_average=200)
        }

    first = Candle(datetime(2026, 9, 2, 9, 15, tzinfo=IST), 100, 105, 99, 104, 1000)
    second = Candle(datetime(2026, 9, 2, 9, 16, tzinfo=IST), 104, 108, 103, 107, 1200)
    engine._fetch_opening_candles = lambda *_args, **_kwargs: [first, second]  # type: ignore[method-assign]

    assert engine.evaluate_opening_candidates() == 0
    row = engine.snapshot()["stocks"][0]
    assert row["possible_candidate"] is False
    assert "09:15/09:16: 09:15 green, 09:16 green" in row["candidate_reason"]


def test_opening_candidate_badge_handles_914_915_opposite_colors(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    engine = ScannerEngine(store)
    engine._client = lambda: object()  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {
            "AAA": StockState(Instrument("AAA", "123", "AAA LTD"), opening_volume_average=200)
        }

    first = Candle(datetime(2026, 9, 2, 9, 14, tzinfo=IST), 100, 105, 99, 104, 1000)
    second = Candle(datetime(2026, 9, 2, 9, 15, tzinfo=IST), 104, 105, 101, 102, 1200)
    engine._fetch_opening_candles = lambda *_args, **_kwargs: [first, second]  # type: ignore[method-assign]

    assert engine.evaluate_opening_candidates() == 1
    row = engine.snapshot()["stocks"][0]
    assert row["possible_candidate"] is True
    assert "Matched 09:14/09:15: 09:14 green, 09:15 red" in row["candidate_reason"]


def test_opening_candidate_prefers_914_when_all_three_labels_exist(tmp_path) -> None:
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    state = StockState(Instrument("AAA", "123", "AAA LTD"), opening_volume_average=200)
    with engine._lock:
        engine._states = {"AAA": state}
    candles = [
        Candle(datetime(2026, 9, 2, 9, 14, tzinfo=IST), 100, 105, 99, 104, 1000),
        Candle(datetime(2026, 9, 2, 9, 15, tzinfo=IST), 104, 105, 101, 102, 1200),
        Candle(datetime(2026, 9, 2, 9, 16, tzinfo=IST), 102, 103, 99, 100, 900),
    ]

    assert engine._apply_opening_candidate("AAA", candles) is True
    row = engine.snapshot()["stocks"][0]
    assert row["today_opening_volume"] == 1000
    assert "Matched 09:14/09:15" in row["candidate_reason"]


def test_quote_ticks_complete_previous_one_minute_candle(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    engine = ScannerEngine(store)
    state = StockState(Instrument("AAA", "123", "AAA LTD"), previous_close=100)
    with engine._lock:
        engine._states = {"AAA": state}

    engine._on_message(None, {"type": "Quote Data", "security_id": 123, "LTP": "101.00", "volume": 1000, "LTT": "15:03:10"})
    engine._on_message(None, {"type": "Quote Data", "security_id": 123, "LTP": "103.00", "volume": 1250, "LTT": "15:03:40"})
    engine._on_message(None, {"type": "Quote Data", "security_id": 123, "LTP": "104.00", "volume": 1400, "LTT": "15:04:02"})

    snapshot = engine.snapshot()["stocks"][0]
    assert snapshot["percent_change"] == 4
    assert snapshot["candle_start"].endswith("T15:03:00+05:30")
    assert snapshot["candle_close"] == 103
    assert snapshot["candle_volume"] == 250
    assert snapshot["candle_turnover"] == 25750


def test_opposite_colors_below_four_times_volume_is_not_candidate(tmp_path) -> None:
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    state = StockState(Instrument("AAA", "123", "AAA LTD"), opening_volume_average=300)
    with engine._lock:
        engine._states = {"AAA": state}

    candles = [
        Candle(datetime(2026, 9, 23, 9, 15, tzinfo=IST), 100, 104, 99, 103, 1000),
        Candle(datetime(2026, 9, 23, 9, 16, tzinfo=IST), 103, 104, 100, 101, 500),
    ]

    assert engine._apply_opening_candidate("AAA", candles) is False
    row = engine.snapshot()["stocks"][0]
    assert row["opening_colors_match"] is True
    assert round(row["volume_multiplier"], 2) == 3.33
    assert row["possible_candidate"] is False


def test_historical_volume_samples_skip_circuit_and_non_trading_days(tmp_path) -> None:
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))

    def candle(day: int, hour: int, minute: int, price: float, volume: int, *, spread: float = 1) -> Candle:
        return Candle(
            datetime(2026, 9, day, hour, minute, tzinfo=IST),
            price,
            price + spread,
            price - spread,
            price,
            volume,
        )

    candles = [
        candle(17, 9, 15, 100, 100), candle(17, 15, 29, 100, 10),
        candle(18, 9, 15, 100, 200), candle(18, 15, 29, 100, 10),
        candle(21, 9, 15, 100, 300), candle(21, 15, 29, 100, 10),
        candle(22, 9, 15, 105, 999, spread=0), candle(22, 15, 29, 105, 10),
    ]

    samples = engine._select_historical_opening_samples(candles, date(2026, 9, 23), 3)

    assert [sample["date"] for sample in samples] == ["2026-09-21", "2026-09-18", "2026-09-17"]
    assert [sample["volume"] for sample in samples] == [300, 200, 100]


def test_historical_volume_samples_accept_914_fallback(tmp_path) -> None:
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    candles = [
        Candle(datetime(2026, 9, 22, 9, 14, tzinfo=IST), 100, 102, 99, 101, 450),
    ]

    samples = engine._select_historical_opening_samples(candles, date(2026, 9, 23), 1)

    assert samples == [{"date": "2026-09-22", "candle_start": "09:14", "volume": 450}]


def test_cache_opening_volume_average_persists_samples_and_checks_today(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    store.update_credentials("client", "token")
    engine = ScannerEngine(store)
    engine._client = lambda: object()  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {"AAA": StockState(Instrument("AAA", "123", "AAA LTD"))}

    samples = [
        {"date": "2026-09-22", "candle_start": "09:15", "volume": 100},
        {"date": "2026-09-21", "candle_start": "09:15", "volume": 200},
        {"date": "2026-09-18", "candle_start": "09:15", "volume": 300},
    ]
    today = [
        Candle(datetime(2026, 9, 23, 9, 15, tzinfo=IST), 100, 104, 99, 103, 1000),
        Candle(datetime(2026, 9, 23, 9, 16, tzinfo=IST), 103, 104, 100, 101, 500),
    ]
    engine._fetch_opening_volume_history = lambda *_args: (samples, today)  # type: ignore[method-assign]

    assert engine.cache_opening_volume_averages() == {"AAA": 200}
    row = engine.snapshot()["stocks"][0]
    assert row["volume_multiplier"] == 5
    assert row["possible_candidate"] is True
    assert store.load().opening_volume_cache["AAA"]["samples"] == samples


def test_volume_average_cache_succeeds_before_opening_pair_is_complete(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    store.update_credentials("client", "token")
    engine = ScannerEngine(store)
    engine._client = lambda: object()  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {"AAA": StockState(Instrument("AAA", "123", "AAA LTD"))}
    samples = [
        {"date": "2026-09-22", "candle_start": "09:15", "volume": 100},
        {"date": "2026-09-21", "candle_start": "09:15", "volume": 200},
        {"date": "2026-09-18", "candle_start": "09:15", "volume": 300},
    ]
    partial_today = [
        Candle(datetime(2026, 9, 23, 9, 15, tzinfo=IST), 100, 102, 99, 101, 500),
    ]
    engine._fetch_opening_volume_history = lambda *_args: (samples, partial_today)  # type: ignore[method-assign]

    assert engine.cache_opening_volume_averages() == {"AAA": 200}
    row = engine.snapshot()["stocks"][0]
    assert row["opening_volume_average"] == 200
    assert row["volume_multiplier"] is None
    assert row["status"] == "volume cached"


def test_snapshot_pins_candidates_first_and_marks_fno(tmp_path) -> None:
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    candidate = StockState(
        Instrument("COALINDIA", "1", "COAL INDIA LTD"),
        percent_change=1,
        possible_candidate=True,
        volume_multiplier=4,
    )
    non_candidate = StockState(
        Instrument("AAA", "2", "AAA LTD"),
        percent_change=20,
        volume_multiplier=8,
    )
    with engine._lock:
        engine._states = {"AAA": non_candidate, "COALINDIA": candidate}

    rows = engine.snapshot()["stocks"]

    assert [row["symbol"] for row in rows] == ["COALINDIA", "AAA"]
    assert rows[0]["is_fno"] is True
    assert rows[1]["is_fno"] is False


def test_volume_cache_stops_batch_on_expired_token(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config.json")
    store.update_credentials("client", "expired")
    engine = ScannerEngine(store)
    engine._client = lambda: object()  # type: ignore[method-assign]
    with engine._lock:
        engine._states = {
            "AAA": StockState(Instrument("AAA", "1", "AAA LTD")),
            "BBB": StockState(Instrument("BBB", "2", "BBB LTD")),
        }
    calls = 0

    def expired(*_args):
        nonlocal calls
        calls += 1
        raise RuntimeError("Invalid_Authentication DH-901: token expired")

    engine._fetch_opening_volume_history = expired  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="DH-901"):
        engine.cache_opening_volume_averages()

    assert calls == 1
    assert engine.snapshot()["stocks"][1]["status"] == "volume cache skipped"
