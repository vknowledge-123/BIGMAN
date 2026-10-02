from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo


def calculate_daily_filter(data: dict, target_date: date) -> dict:
    """Use four completed daily bars, strictly before the scan session."""
    timestamps = data.get("timestamp") or []
    closes = data.get("close") or []
    volumes = data.get("volume") or []
    if not (len(timestamps) == len(closes) == len(volumes)):
        raise ValueError("Dhan daily history has mismatched timestamp, close or volume arrays")
    sessions: dict[date, dict] = {}
    for timestamp, raw_close, raw_volume in zip(timestamps, closes, volumes):
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
            if session in sessions and sessions[session] != bar:
                raise ValueError("Conflicting duplicate daily candles")
            sessions[session] = bar
        except (ValueError, TypeError, OverflowError, OSError) as exc:
            raise ValueError(f"Invalid Dhan daily candle: {exc}") from exc
    if len(sessions) < 4:
        raise ValueError("Four completed daily candles are required for the previous-day filter")
    bars = [sessions[session] for session in sorted(sessions)[-4:]]
    samples, previous = bars[:3], bars[3]
    volume_sum = sum(bar["volume"] for bar in samples)
    if volume_sum <= 0:
        raise ValueError("Previous three daily volumes have a zero average")
    average = volume_sum / 3
    prior_close = Decimal(str(samples[-1]["close"]))
    previous_close = Decimal(str(previous["close"]))
    percent_change = (previous_close - prior_close) / prior_close * 100
    normal_volume = previous["volume"] * 3 <= volume_sum * 4
    price_exception = not normal_volume and percent_change <= Decimal("1")
    return {
        "session_date": target_date.isoformat(),
        "previous_date": previous["date"],
        "previous_volume": previous["volume"],
        "previous_close": previous["close"],
        "prior_close": float(prior_close),
        "average": average,
        "multiplier": previous["volume"] / average,
        "percent_change": float(percent_change),
        "samples": samples,
        "passes": normal_volume or price_exception,
        "price_exception": price_exception,
    }
