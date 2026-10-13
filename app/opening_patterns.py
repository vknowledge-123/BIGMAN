"""Opening-candle patterns evaluated from completed, dated minute candles."""
from datetime import time


def later_candles(first, candles):
    return sorted({bar.start: bar for bar in candles
                   if bar.start.date() == first.start.date()
                   and first.end <= bar.start and bar.start.time() < time(15, 30)}.values(),
                  key=lambda bar: bar.start)


def first_high_broken(first, candles):
    return any(bar.high > first.high for bar in later_candles(first, candles))


def retest_sequence(first, candles):
    """First red, then only green candles through the first strict high break.

    A red/doji before the break invalidates the sequence permanently. A gap is
    unresolved, not evidence of an uninterrupted sequence. Bars after a confirmed
    break do not undo the event. The breaking candle must itself close green.
    """
    result = {"retest_break": False, "retest_break_at": None,
              "retest_status": "waiting", "retest_reason": "Waiting for green candles to break the first high"}
    if first.color != "red":
        return {**result, "retest_status": "filtered", "retest_reason": "Retest Break requires a red first candle"}
    expected = first.end
    for bar in later_candles(first, candles):
        if bar.start != expected:
            return {**result, "retest_status": "unresolved", "retest_reason": f"Missing completed candle at {expected:%H:%M}"}
        if bar.color != "green":
            return {**result, "retest_status": "rejected", "retest_reason": f"{bar.start:%H:%M} {bar.color} candle interrupted the green sequence"}
        if bar.high > first.high:
            return {"retest_break": True, "retest_break_at": bar.start.isoformat(timespec="seconds"),
                    "retest_status": "confirmed",
                    "retest_reason": f"{bar.start:%H:%M} closed green and broke first-candle high {first.high:g}; all intervening candles green"}
        expected = bar.end
    return result
