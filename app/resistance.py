"""Session-bound daily swing resistance. No intraday/future candles select a level."""
from datetime import date
from decimal import Decimal
from functools import lru_cache
import math

from .schemas import VolumeFilterSettings


def history_days(settings: VolumeFilterSettings) -> int:
    return max(90, (settings.resistance_lookback + settings.resistance_left) * 2 + 30) if settings.resistance_filter else 90


def missing_history(daily: dict | None, session: date, settings: VolumeFilterSettings) -> str | None:
    if not settings.resistance_filter:
        return None
    try:
        if not daily or daily.get("session_date") != session.isoformat():
            raise ValueError()
        if daily.get("resistance_capacity", 0) < settings.resistance_lookback + settings.resistance_left:
            raise ValueError()
        rows = daily["resistance_history"]
        dates = [date.fromisoformat(row["date"]) for row in rows]
        if not dates or dates != sorted(set(dates)) or dates[-1] >= session or dates[-1].isoformat() != daily["previous_date"]:
            raise ValueError()
        for row in rows:
            high, low, close = (float(row[key]) for key in ("high", "low", "close"))
            if not all(math.isfinite(x) and x > 0 for x in (high, low, close)) or not low <= close <= high:
                raise ValueError()
    except (KeyError, TypeError, ValueError, OverflowError):
        return "Daily resistance data pending: cache completed daily highs, lows and closes for this session"
    return None


@lru_cache(maxsize=2048)
def _select(rows: tuple, lookback: int, left: int, right: int, min_age: int,
            max_age: int, pullback_enabled: bool, pullback_min: float) -> tuple | None:
    n = len(rows)
    previous_close = rows[-1][3]
    eligible = []
    for i in range(max(left, n - lookback), n - right):
        day, high, _, _ = rows[i]
        age = n - i  # Previous trading session is age 1.
        if not min_age <= age <= max_age:
            continue
        neighbours = rows[i-left:i] + rows[i+1:i+right+1]
        if any(high <= bar[1] for bar in neighbours):
            continue
        later = rows[i+1:]
        if high < previous_close or any(bar[3] > high for bar in later):
            continue  # A subsequent completed daily close already broke this level.
        retreat = (Decimal(str(high)) - Decimal(str(min(bar[2] for bar in later)))) / Decimal(str(high)) * 100
        if pullback_enabled and retreat < Decimal(str(pullback_min)):
            continue
        eligible.append((high, age, day, float(retreat)))
    return min(eligible) if eligible else None  # Nearest overhead level; newest for equal highs.


def selection(daily: dict | None, session: date, settings: VolumeFilterSettings) -> dict:
    result = dict(resistance_level=None, resistance_threshold=None, resistance_date=None,
                  resistance_age=None, resistance_pullback_percent=None, resistance_status="off")
    if not settings.resistance_filter:
        return result
    if missing_history(daily, session, settings):
        return {**result, "resistance_status": "unresolved"}
    rows = tuple((bar["date"], float(bar["high"]), float(bar["low"]), float(bar["close"]))
                 for bar in daily["resistance_history"])
    level = _select(rows, settings.resistance_lookback, settings.resistance_left,
                    settings.resistance_right, settings.resistance_min_age, settings.resistance_max_age,
                    settings.resistance_pullback, settings.resistance_pullback_min)
    if level is None:
        return {**result, "resistance_status": "no_level"}
    high, age, day, pullback = level
    threshold = Decimal(str(high)) * (1 + Decimal(str(settings.resistance_buffer)) / 100)
    return dict(resistance_level=high, resistance_threshold=float(threshold), resistance_date=day,
                resistance_age=age, resistance_pullback_percent=pullback, resistance_status="ready")


def above(price: float | None, selected: dict) -> bool:
    threshold = selected.get("resistance_threshold")
    return bool(price is not None and math.isfinite(price) and threshold is not None
                and Decimal(str(price)) > Decimal(str(threshold)))


def replay_badges(candles, first, selected: dict) -> dict:
    bars = sorted((bar for bar in candles if bar.start.date() == first.start.date()
                   and first.start <= bar.start < first.start.replace(hour=15, minute=30)), key=lambda bar: bar.start)
    breaks = [bar for bar in bars if bar.color == "green" and above(bar.close, selected)]
    crosses = [(index, bar) for index in (1, 2) for bar in bars
               if (bar.start - first.start).total_seconds() == (index - 1) * 60
               and selected.get("resistance_level") is not None
               and bar.open < selected["resistance_level"] and above(bar.close, selected)]
    return dict(resistance_break=bool(breaks), resistance_break_at=breaks[0].end.isoformat() if breaks else None,
                resistance_break_open=bool(crosses), resistance_break_open_candle=crosses[0][0] if crosses else None)
