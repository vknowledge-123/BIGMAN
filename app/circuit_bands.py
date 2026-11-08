"""Conservative classification of today's fixed cash-equity circuit limits."""
from datetime import date
from decimal import Decimal, InvalidOperation


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def reference_close(quote, daily, session):
    # Dhan documents net_change as LTP minus the previous closing price.
    price, change = number(quote.get('last_price')), number(quote.get('net_change'))
    if price is not None and price > 0 and change is not None and price - change > 0:
        return float(price - change)
    try:
        if daily and daily.get('session_date') == session.isoformat() and date.fromisoformat(daily['previous_date']) < session:
            close = number(daily.get('previous_close'))
            if close is not None and close > 0:
                return float(close)
    except (KeyError, ValueError, TypeError):
        pass
    return None


def classify(upper, lower, reference, *, fresh, is_fno=False, inconsistent=False):
    result = dict(circuit_band_percent=None, circuit_band_status='unverified', circuit_band_eligible=False)
    if is_fno:
        return {**result, 'circuit_band_status': 'dynamic'}
    if not fresh:
        return {**result, 'circuit_band_status': 'pending_or_stale'}
    high, low, close = map(number, (upper, lower, reference))
    if inconsistent or any(x is None or x <= 0 for x in (high, low, close)):
        return result
    if not low < close < high:
        return result
    # Verify BOTH limits against the same reference, never the distance to LTP.
    # Allow <= 5 paise rounding, capped at 0.1% of reference for low-price shares.
    # Unrecognised/asymmetric ranges stay unknown instead of rounding up to 20%.
    tolerance = min(Decimal('0.05'), close * Decimal('0.001')) + Decimal('0.000000001')
    matches = [band for band in (2, 5, 10, 20)
               if abs(high - close * (1 + Decimal(band) / 100)) <= tolerance
               and abs(low - close * (1 - Decimal(band) / 100)) <= tolerance]
    if len(matches) != 1:
        return result
    band = matches[0]
    return dict(circuit_band_percent=band, circuit_band_status='verified', circuit_band_eligible=band >= 20)
