from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo


def _daily_price(values: list, index: int) -> float | None:
    try:
        price = float(values[index])
        return price if math.isfinite(price) and price > 0 else None
    except (IndexError, TypeError, ValueError, OverflowError):
        return None


def calculate_daily_filter(data: dict, target_date: date, volume_limit: float = 4.0,
                           resistance_capacity: int = 0) -> dict:
    """Use completed sessions strictly before the scan date; cache opening-filter inputs."""
    timestamps = data.get("timestamp") or []
    closes = data.get("close") or []
    volumes = data.get("volume") or []
    highs = data.get("high") or []
    lows = data.get("low") or []
    opens = data.get("open") or []
    if not (len(timestamps) == len(closes) == len(volumes)):
        raise ValueError("Dhan daily history has mismatched timestamp, close or volume arrays")
    sessions: dict[date, dict] = {}
    for index, (timestamp, raw_close, raw_volume) in enumerate(zip(timestamps, closes, volumes)):
        try:
            session = datetime.fromtimestamp(float(timestamp), ZoneInfo("Asia/Kolkata")).date()
            if session >= target_date:
                continue
            close, volume = float(raw_close), float(raw_volume)
            if not math.isfinite(close) or close <= 0 or not math.isfinite(volume) or volume < 0:
                raise ValueError("Invalid daily close or volume")
            if not volume.is_integer():
                raise ValueError("Daily volume must be a whole number")
            bar = {"date": session.isoformat(), "close": close, "volume": int(volume)}
            high = _daily_price(highs, index) if len(highs) == len(timestamps) else None
            low = _daily_price(lows, index) if len(lows) == len(timestamps) else None
            if high is not None and high < close:
                high = None
            if low is not None and low > close:
                low = None
            opening = _daily_price(opens, index) if len(opens) == len(timestamps) else None
            bar.update(high=high, low=low, open=opening)
            if session in sessions and sessions[session] != bar:
                raise ValueError("Conflicting duplicate daily candles")
            sessions[session] = bar
        except (ValueError, TypeError, OverflowError, OSError) as exc:
            raise ValueError(f"Invalid Dhan daily candle: {exc}") from exc
    if len(sessions) < 4:
        raise ValueError("Four completed daily candles are required for the previous-day filter")
    bars = [sessions[session] for session in sorted(sessions)[-4:]]
    five_day_closes = [{"date": sessions[session]["date"], "close": sessions[session]["close"]}
                       for session in sorted(sessions)[-5:]]
    samples, previous = bars[:3], bars[3]
    volume_sum = sum(bar["volume"] for bar in samples)
    if volume_sum <= 0:
        raise ValueError("Previous three daily volumes have a zero average")
    average = volume_sum / 3
    prior_close = Decimal(str(samples[-1]["close"]))
    previous_close = Decimal(str(previous["close"]))
    percent_change = (previous_close - prior_close) / prior_close * 100
    normal_volume = Decimal(previous["volume"] * 3) <= Decimal(volume_sum) * Decimal(str(volume_limit))
    price_exception = not normal_volume and percent_change <= Decimal("1")
    return {
        **({"resistance_capacity": resistance_capacity,
            "resistance_history": [sessions[day] for day in sorted(sessions)[-resistance_capacity:]]}
           if resistance_capacity else {}),
        "twenty_day_closes": [{"date": sessions[day]["date"], "close": sessions[day]["close"]}
                              for day in sorted(sessions)[-20:]],
        "last_two_day_candles": [{key: sessions[day][key] for key in ("date", "open", "close")}
                                 for day in sorted(sessions)[-2:]],
        "five_day_closes": five_day_closes,
        "five_day_highest_close": max(item["close"] for item in five_day_closes) if len(five_day_closes) == 5 else None,
        "volume_limit": volume_limit,
        "session_date": target_date.isoformat(),
        "previous_date": previous["date"],
        "previous_volume": previous["volume"],
        "previous_close": previous["close"],
        "previous_high": previous["high"],
        "previous_low": previous["low"],
        "prior_close": float(prior_close),
        "average": average,
        "multiplier": previous["volume"] / average,
        "percent_change": float(percent_change),
        "samples": samples,
        "passes": normal_volume or price_exception,
        "price_exception": price_exception,
    }


def apply_daily_volume_limit(daily: dict | None, volume_limit: float) -> dict | None:
    """Re-evaluate cached inputs without downloading history or changing its scan date."""
    if not daily or daily.get("volume_limit", 4.0) == volume_limit:
        return daily
    samples = daily.get("samples") or []
    if len(samples) == 3 and all("volume" in sample for sample in samples):
        volume_sum = sum(Decimal(str(sample["volume"])) for sample in samples)
        normal = Decimal(str(daily["previous_volume"])) * 3 <= volume_sum * Decimal(str(volume_limit))
    else:
        normal = Decimal(str(daily["multiplier"])) <= Decimal(str(volume_limit))
    if daily.get("prior_close") and daily.get("previous_close"):
        prior = Decimal(str(daily["prior_close"]))
        percent_change = (Decimal(str(daily["previous_close"])) - prior) / prior * 100
    else:
        percent_change = Decimal(str(daily["percent_change"]))
    price_exception = not normal and percent_change <= Decimal("1")
    return {**daily, "volume_limit": volume_limit, "passes": normal or price_exception,
            "price_exception": price_exception}
