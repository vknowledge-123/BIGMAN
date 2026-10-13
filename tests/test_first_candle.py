from datetime import datetime, timedelta

import pytest

from app.daily_filter import calculate_daily_filter
from app.dhan_scanner import Candle, Instrument, ScannerEngine, StockState
from app.schemas import BacktestRow, StockRow
from app.storage import ConfigStore
from test_daily_filter import IST, SESSION, daily_data, pair


@pytest.mark.parametrize("color,level,expected", [
    ("green", 100.5, True), ("green", 100, False), ("green", 101, False),
    ("green", 99, False), ("green", 102, False), ("green", None, False),
    ("red", 99.5, True), ("red", 100, False), ("red", 99, False),
    ("red", 98, False), ("red", 101, False), ("red", None, False),
])
@pytest.mark.parametrize("qualified", [True, False])
def test_strict_crosses_match_live_and_backtest_without_second_candle(tmp_path, color, level, expected, qualified):
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    daily = calculate_daily_filter(daily_data(), SESSION)
    daily.update(previous_high=level if color == "green" else 103,
                 previous_low=level if color == "red" else 98)
    instrument = Instrument("AAA", "1", "AAA")
    state = StockState(instrument, opening_volume_average=100_000, daily_filter=daily)
    engine._states = {"AAA": state}
    candles = pair(color, None, color == "red", 400_000 if qualified else 399_000)
    engine._apply_opening_candidate("AAA", candles)
    history = [Candle(candles[0].start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)]
    live = StockRow.model_validate(engine.snapshot()["stocks"][0]).model_dump()
    backtest = BacktestRow.model_validate(engine._build_backtest_row(instrument, SESSION, history + candles, daily)).model_dump()
    for row in (live, backtest):
        assert row["possible_candidate"] is (qualified and color == "green")
        assert row["redwala_gira"] is (color == "red")
        assert row["previous_day_high_cross"] is (expected and qualified and color == "green")
        assert row["previous_day_low_cross"] is (expected and color == "red")


def test_previous_levels_use_last_completed_session_and_ignore_future():
    data = daily_data()
    for offset in (0, 1):
        data["timestamp"].append(datetime(2026, 10, 1 + offset, tzinfo=IST).timestamp())
        for field, value in {"high": 900, "low": 800, "close": 850, "volume": 999999}.items():
            data[field].append(value)
    result = calculate_daily_filter({key: list(reversed(values)) for key, values in data.items()}, SESSION)
    assert (result["previous_date"], result["previous_high"], result["previous_low"]) == ("2026-09-30", 103, 99.5)


@pytest.mark.parametrize("bad", [None, 0, -1, float("nan"), float("inf")])
def test_invalid_levels_cannot_create_cross_badges(bad):
    data = daily_data()
    data["high"][-1] = data["low"][-1] = bad
    daily = calculate_daily_filter(data, SESSION)
    assert daily["previous_high"] is None
    assert daily["previous_low"] is None
    assert daily["passes"] is True


def test_daily_and_minute_requests_share_023_second_spacing(tmp_path, monkeypatch):
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    clock = [100.0]
    starts = []
    monkeypatch.setattr("app.dhan_scanner.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.dhan_scanner.time.sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    class Client:
        def historical_daily_data(self, *args, **kwargs):
            starts.append(clock[0])
            return {"status": "success"}

        intraday_minute_data = historical_daily_data

    client = Client()
    for _ in range(3):
        engine._historical_daily_with_retry(client)
        engine._intraday_with_retry(client)
    assert starts == pytest.approx([100 + i * 0.23 for i in range(6)])


def test_pending_refresh_skips_confirmed_stock_and_has_no_per_stock_sleep(tmp_path, monkeypatch):
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    session = datetime.now(IST).date()
    daily = calculate_daily_filter(daily_data(), SESSION)
    daily["session_date"] = session.isoformat()
    engine._states = {symbol: StockState(Instrument(symbol, str(i), symbol), opening_volume_average=100_000,
                                        daily_filter=daily) for i, symbol in enumerate(("AAA", "BBB", "CCC"))}
    engine._states["AAA"].signal_session = session
    engine._states["AAA"].confirmation_status = "confirmed"
    calls = []
    sleeps = []
    monkeypatch.setattr("app.dhan_scanner.time.sleep", sleeps.append)
    monkeypatch.setattr(engine, "refresh_circuit_limits", lambda *_: None)

    def fetch(client, instrument):
        calls.append(instrument.symbol)
        return [Candle(datetime.combine(session, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15),
                       100, 102, 100, 101, 400_000)]

    monkeypatch.setattr(engine, "_fetch_opening_candles", fetch)
    assert engine.evaluate_opening_candidates(object(), only_pending=True) == 2
    assert calls == ["BBB", "CCC"]
    assert sleeps == []
