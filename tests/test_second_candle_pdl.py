from datetime import datetime, timedelta

import pytest

from app.daily_filter import calculate_daily_filter
from app.dhan_scanner import Candle, Instrument, ScannerEngine, StockState
from app.schemas import BacktestRow, StockRow
from app.storage import ConfigStore
from test_daily_filter import IST, SESSION, daily_data


@pytest.mark.parametrize('opening,close,offset,level,eligible,expected', [
    (99, 97, 1, 98, True, True),
    (98, 97, 1, 98, True, False),  # Open touches PDL.
    (99, 98, 1, 98, True, False),  # Close touches PDL.
    (99, 99, 1, 98, True, False),  # Wick below PDL only.
    (97, 96, 1, 98, True, False),  # Opens below PDL.
    (99, 97, 2, 98, True, False),  # Third candle cannot replace missing second.
    (99, 97, 1, None, True, False),
    (99, 97, 1, 98, False, False),
])
def test_second_pdl_cross_live_backtest_and_schema(tmp_path, opening, close, offset, level, eligible, expected):
    engine = ScannerEngine(ConfigStore(tmp_path / 'config.json'))
    daily = calculate_daily_filter(daily_data(), SESSION)
    daily['previous_low'] = level
    instrument = Instrument('AAA', '1', 'AAA')
    engine._states = {'AAA': StockState(instrument, opening_volume_average=100_000, daily_filter=daily)}
    first = Candle(datetime.combine(SESSION, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15),
                   100, 100, 99, 99, 400_000 if eligible else 1)
    second = Candle(first.start + timedelta(minutes=offset), opening, max(opening, close),
                    min(96, close), close, 100_000)
    history = [Candle(first.start - timedelta(days=n), 100, 102, 98, 101, 100_000) for n in (1, 2, 3)]
    engine._apply_opening_candidate('AAA', [first, second])
    live = StockRow.model_validate(engine.snapshot()['stocks'][0])
    backtest = BacktestRow.model_validate(engine._build_backtest_row(instrument, SESSION, history + [first, second], daily))
    for row in (live, backtest):
        assert row.previous_day_low_cross_second_candle is expected
        assert row.previous_day_low_cross is False


def test_second_cross_waits_for_close_and_requires_current_daily_levels(monkeypatch):
    start = datetime.combine(SESSION, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15)
    now = [start + timedelta(minutes=1, seconds=59)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now[0]

    monkeypatch.setattr('app.dhan_scanner.datetime', Clock)
    first = Candle(start, 100, 100, 99, 99, 400_000)
    second = Candle(first.end, 99, 99, 97, 97, 100_000)
    daily = {'session_date': SESSION.isoformat(), 'previous_low': 98}
    check = ScannerEngine._second_candle_pdl_cross
    assert not check(first, [second], daily, SESSION, True)
    now[0] += timedelta(seconds=1)
    assert check(first, [second], daily, SESSION, True)
    assert not check(first, [second], {**daily, 'session_date': '2026-09-30'}, SESSION, True)
    assert not check(first, [], daily, SESSION, True)
