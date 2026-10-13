"""Optional daily-history checks for Candidates and Retest Break; not Redwala."""
from datetime import date
import math

from .schemas import VolumeFilterSettings


def _samples(daily: dict | None, session: date, key: str, count: int,
             *, need_open: bool = False) -> list[dict] | None:
    if not daily or daily.get("session_date") != session.isoformat():
        return None
    rows = daily.get(key)
    if not isinstance(rows, list) or len(rows) != count:
        return None
    try:
        dates = [date.fromisoformat(row["date"]) for row in rows]
        if (dates != sorted(set(dates)) or any(day >= session for day in dates)
                or dates[-1].isoformat() != daily.get("previous_date")):
            return None
        fields = ("open", "close") if need_open else ("close",)
        if any(not math.isfinite(float(row[field])) or float(row[field]) <= 0
               for row in rows for field in fields):
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return rows


def missing_history(daily: dict | None, session: date, settings: VolumeFilterSettings) -> str | None:
    missing = []
    if settings.monthly_filter and _samples(daily, session, "twenty_day_closes", 20) is None:
        missing.append("Monthly Filter needs 20 completed trading-session closes")
    if settings.last_two_days_filter and _samples(daily, session, "last_two_day_candles", 2, need_open=True) is None:
        missing.append("Last 2 Days Filter needs opens and closes for two completed trading sessions")
    return "; ".join(missing) or None


def evaluate(daily: dict | None, session: date, opening: float | None,
             settings: VolumeFilterSettings) -> dict:
    missing = missing_history(daily, session, settings)
    if missing:
        return {"passes": False, "resolved": False, "reason": missing}
    passed = True
    reasons = []
    valid_open = opening is not None and math.isfinite(opening) and opening > 0
    if settings.monthly_filter:
        level = max(float(row["close"]) for row in daily["twenty_day_closes"])
        matches = valid_open and opening > level
        passed = passed and matches
        reasons.append(f"Monthly Filter: open > prior 20-session highest close {level:g} ({'pass' if matches else 'fail'})")
    if settings.last_two_days_filter:
        rows = daily["last_two_day_candles"]
        both_green = all(float(row["close"]) > float(row["open"]) for row in rows)
        if both_green:
            reasons.append("Last 2 Days Filter: both candles green; no additional opening condition")
        else:
            level = max(float(row["close"]) for row in rows)
            matches = valid_open and opening > level
            passed = passed and matches
            reasons.append(f"Last 2 Days Filter: red or doji candle; open > prior 2-session highest close {level:g} ({'pass' if matches else 'fail'})")
    return {"passes": bool(passed), "resolved": True, "reason": "; ".join(reasons)}
