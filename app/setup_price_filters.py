"""Optional price filters with explicit setup scope and session-bound cached inputs."""
from datetime import date
from decimal import Decimal, InvalidOperation

from .schemas import VolumeFilterSettings


def missing_history(daily: dict | None, session: date, settings: VolumeFilterSettings,
                    setup: str) -> str | None:
    gap = setup == "redwala" and settings.redwala_open_previous_close
    pdhl = setup == "possible" and settings.pdhl_filter
    if not (gap or pdhl):
        return None
    label = "Redwala Open / Previous Close" if gap else "PDHL"
    fields = ("previous_close",) if gap else ("previous_high", "previous_low")
    try:
        if not daily or daily.get("session_date") != session.isoformat():
            raise ValueError()
        if date.fromisoformat(daily["previous_date"]) >= session:
            raise ValueError()
        values = [Decimal(str(daily[key])) for key in fields]
        if any(not value.is_finite() or value <= 0 for value in values):
            raise ValueError()
        if pdhl and values[0] < values[1]:
            raise ValueError()
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return f"{label} needs valid previous trading-day {'close' if gap else 'high and low'} for this session"
    return None


def evaluate(daily: dict | None, session: date, opening: float, close: float,
             settings: VolumeFilterSettings, setup: str) -> dict:
    missing = missing_history(daily, session, settings, setup)
    if missing:
        return {"passes": False, "resolved": False, "reason": missing}
    if setup == "redwala" and settings.redwala_open_previous_close:
        previous = Decimal(str(daily["previous_close"]))
        op, cl = Decimal(str(opening)), Decimal(str(close))
        gap = (op - previous) / previous * 100
        passes = cl < previous < op and gap <= Decimal(str(settings.redwala_open_gap_max))
        reason = (f"Redwala Open / Previous Close: gap {gap:.4f}% <= {settings.redwala_open_gap_max:g}%; "
                  f"first open > previous close {previous:g} > first close ({'pass' if passes else 'fail'})")
    elif setup == "possible" and settings.pdhl_filter:
        high, low = Decimal(str(daily["previous_high"])), Decimal(str(daily["previous_low"]))
        spread = (high - low) / low * 100
        passes = spread <= Decimal(str(settings.pdhl_max))
        reason = f"PDHL: (previous high - low) / low = {spread:.4f}% <= {settings.pdhl_max:g}% ({'pass' if passes else 'fail'})"
    else:
        return {"passes": True, "resolved": True, "reason": ""}
    return {"passes": bool(passes), "resolved": True, "reason": reason}
