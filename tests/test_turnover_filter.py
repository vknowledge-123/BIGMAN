from datetime import datetime, timedelta

import pytest

from app.dhan_scanner import Candle, Instrument, ScannerEngine, StockState
from app.schemas import BacktestRow, StockRow
from app.storage import ConfigStore
from test_daily_filter import IST, SESSION, daily_data
from app.daily_filter import calculate_daily_filter


@pytest.mark.parametrize("color", ["green", "red"])
@pytest.mark.parametrize("volume,qualifies", [(299_999, False), (300_000, False), (300_001, True)])
def test_three_crore_strict_boundary_in_live_backtest_and_counts(tmp_path, monkeypatch, color, volume, qualifies):
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    daily = calculate_daily_filter(daily_data(), SESSION)
    daily.update(previous_high=99.5, previous_low=100.5)
    instrument = Instrument("AAA", "1", "AAA")
    state = StockState(instrument, opening_volume_average=10_000, daily_filter=daily, ltp=9999)
    engine._states = {"AAA": state}
    first = Candle(datetime(2026, 10, 1, 9, 15, tzinfo=IST),
                   99 if color == "green" else 101, 101, 98, 100, volume)
    # A large later candle and LTP must never rescue insufficient first-minute turnover.
    second = Candle(first.end, 100, 1000, 100, 1000, 1_000_000)
    engine._apply_opening_candidate("AAA", [first, second])
    live = StockRow.model_validate(engine.snapshot()["stocks"][0]).model_dump()
    history = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 10_000) for n in (1, 2, 3)]
    monkeypatch.setattr(engine, "_client", lambda: object())
    monkeypatch.setattr(engine, "_fetch_daily_filter", lambda *_: daily)
    monkeypatch.setattr(engine, "_fetch_backtest_history", lambda *_: history + [first, second])
    result = engine.backtest_date(SESSION)
    backtest = BacktestRow.model_validate(result["stocks"][0]).model_dump()
    assert result["qualified_count"] == int(qualifies)
    assert result["candidate_count"] == int(qualifies and color == "green")
    assert result["redwala_count"] == int(qualifies and color == "red")
    for row in (live, backtest):
        assert row["first_candle_turnover"] == volume * 100
        assert row["qualifies_scan"] is qualifies
        assert row["possible_candidate"] is (qualifies and color == "green")
        assert row["redwala_gira"] is (qualifies and color == "red")
        assert row["previous_day_high_cross"] is (qualifies and color == "green")
        assert row["previous_day_low_cross"] is (qualifies and color == "red")
        assert f"30,000,000.00 INR ({'pass' if qualifies else 'fail'})" in row["candidate_reason"]
