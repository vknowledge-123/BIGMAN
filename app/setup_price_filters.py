"""Optional price filters with explicit setup scope and session-bound cached inputs."""
from datetime import date
from decimal import Decimal, InvalidOperation

from .schemas import VolumeFilterSettings


def missing_history(daily: dict | None, session: date, settings: VolumeFilterSettings,
                    setup: str) -> str | None:
    gap = setup == "redwala" and settings.redwala_open_previous_close
    pdhl = setup == "possible" and settings.pdhl_filter
    possible_gap = setup == "possible" and settings.possible_open_pre_close
    if not (gap or pdhl or possible_gap):
        return None
    labels = (["Redwala Open / Previous Close"] if gap else []) + (["Possible Candidates Open / Previous Close"] if possible_gap else []) + (["PDHL"] if pdhl else [])
    label = "; ".join(labels)
    fields = (("previous_close",) if gap or possible_gap else ()) + (("previous_high", "previous_low") if pdhl else ())
    try:
        if not daily or daily.get("session_date") != session.isoformat():
            raise ValueError()
        if date.fromisoformat(daily["previous_date"]) >= session:
            raise ValueError()
        values = [Decimal(str(daily[key])) for key in fields]
        if any(not value.is_finite() or value <= 0 for value in values):
            raise ValueError()
        if pdhl and Decimal(str(daily["previous_high"])) < Decimal(str(daily["previous_low"])):
            raise ValueError()
    except (KeyError, TypeError, ValueError, InvalidOperation):
        needed = "close, high and low" if possible_gap and pdhl else "close" if gap or possible_gap else "high and low"
        return f"{label} needs valid previous trading-day {needed} for this session"
    return None


def evaluate(daily: dict | None, session: date, opening: float, close: float,
             settings: VolumeFilterSettings, setup: str) -> dict:
    missing = missing_history(daily, session, settings, setup)
    if missing:
        return {"passes": False, "resolved": False, "reason": missing}
    if setup == "redwala" and settings.redwala_open_previous_close:
        previous = Decimal(str(daily["previous_close"]))
        op, cl = Decimal(str(opening)), Decimal(str(close))
        open_gap = abs(op - previous) / previous * 100
        close_gap = abs(cl - previous) / previous * 100
        open_allowed = op > previous
        opening_rule = "first open > previous close"
        if settings.redwala_open_tolerance:
            tolerance = Decimal(str(settings.redwala_open_tolerance_max))
            open_allowed = (op - previous) / previous * 100 >= -tolerance
            opening_rule = f"first open at/above previous close or within {tolerance:g}% below it"
        passes = cl < previous and open_allowed and min(open_gap, close_gap) <= Decimal(str(settings.redwala_open_gap_max))
        reason = (f"Redwala Open or Close / Previous Close: open distance {open_gap:.4f}%, "
                  f"close distance {close_gap:.4f}%; either <= {settings.redwala_open_gap_max:g}%; "
                  f"{opening_rule}; first close < previous close {previous:g} ({'pass' if passes else 'fail'})")
    elif setup == "possible" and (settings.pdhl_filter or settings.possible_open_pre_close):
        checks, reasons = [], []
        if settings.pdhl_filter:
            high, low = Decimal(str(daily["previous_high"])), Decimal(str(daily["previous_low"]))
            spread = (high - low) / low * 100
            check = spread <= Decimal(str(settings.pdhl_max))
            checks.append(check)
            reasons.append(f"PDHL: (previous high - low) / low = {spread:.4f}% <= {settings.pdhl_max:g}% ({'pass' if check else 'fail'})")
        if settings.possible_open_pre_close:
            previous = Decimal(str(daily["previous_close"]))
            distance = abs(Decimal(str(opening)) - previous) / previous * 100
            check = distance <= Decimal(str(settings.possible_open_pre_close_max))
            checks.append(check)
            reasons.append(f"Possible Candidates Open / Previous Close: absolute opening distance {distance:.4f}% <= {settings.possible_open_pre_close_max:g}% ({'pass' if check else 'fail'})")
        passes, reason = all(checks), "; ".join(reasons)
    else:
        return {"passes": True, "resolved": True, "reason": ""}
    return {"passes": bool(passes), "resolved": True, "reason": reason}
