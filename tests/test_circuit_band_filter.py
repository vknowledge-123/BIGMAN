"""Quote -> dated reference -> API model -> live eligibility. No broker access."""
from datetime import datetime, timedelta

import pytest

from app.circuit_bands import classify, reference_close
from app.schemas import StateOut
from test_circuits import QuoteClient, scanner, IST


@pytest.mark.parametrize('band', [2, 5, 10, 20])
def test_verify_both_sides_not_ltp_distance(scanner, band):
    client = QuoteClient(100 + band, 100 - band, 100 + band / 2)
    client.item['net_change'] = band / 2
    scanner.refresh_circuit_limits(client)
    row = StateOut(**scanner.snapshot()).stocks[0]
    assert row.circuit_band_status == 'verified'
    assert row.circuit_band_percent == band
    assert row.circuit_band_eligible is (band >= 20)
    assert row.circuit_reference_close == 100
    assert row.possible_candidate and row.qualifies_scan  # Display gate, not qualification.
    assert row.upper_circuit_distance_percent == pytest.approx((100 + band - row.ltp) / row.ltp * 100)
    assert row.lower_circuit_distance_percent == pytest.approx((row.ltp - 100 + band) / row.ltp * 100)


def test_ltp_changes_do_not_change_verified_band_or_fetch_again(scanner):
    client = QuoteClient(120, 80, 110)
    client.item['net_change'] = 10
    scanner.refresh_circuit_limits(client)
    scanner._states['AAA'].ltp = 120
    scanner.refresh_circuit_limits(client)
    row = scanner.snapshot()['stocks'][0]
    assert row['circuit_band_eligible'] and row['circuit_band_percent'] == 20
    assert row['upper_circuit_distance_percent'] == 0
    assert row['lower_circuit_distance_percent'] == pytest.approx(100 / 3)
    assert len(client.calls) == 1


@pytest.mark.parametrize('upper,lower,reference', [
    (120, None, 100), (None, 80, 100), (120, 90, 100), (119, 81, 100),
    (119.5, 80.5, 100), (120, 80, None), (80, 120, 100), (120, 80, 0),
    (float('inf'), 80, 100), (120, float('nan'), 100), (120, 80, float('nan')),
])
def test_incomplete_asymmetric_invalid_or_unrecognised_band_is_unknown(upper, lower, reference):
    result = classify(upper, lower, reference, fresh=True)
    assert result == dict(circuit_band_percent=None, circuit_band_status='unverified', circuit_band_eligible=False)


def test_rounding_and_low_price_safeguard():
    assert classify(148.15, 98.75, 123.45, fresh=True)['circuit_band_eligible']
    assert classify(.12, .08, .10, fresh=True)['circuit_band_eligible']
    assert not classify(.11, .09, .10, fresh=True)['circuit_band_eligible']
    assert not classify(120, 80, 100, fresh=True, inconsistent=True)['circuit_band_eligible']


def test_reference_prefers_same_quote_change_and_dated_history_only():
    session = datetime.now(IST).date()
    daily = dict(session_date=session.isoformat(), previous_date=(session-timedelta(days=1)).isoformat(), previous_close=99)
    assert reference_close(dict(last_price=110, net_change=10), daily, session) == 100
    assert reference_close(dict(last_price=90, net_change=-10), daily, session) == 100
    assert reference_close(dict(last_price=100, net_change=0), None, session) == 100
    assert reference_close({}, daily, session) == 99
    assert reference_close({}, {**daily, 'session_date': '2000-01-01'}, session) is None
    assert reference_close({}, {**daily, 'previous_date': session.isoformat()}, session) is None
    assert reference_close({}, {**daily, 'previous_close': float('nan')}, session) is None
    assert reference_close({}, None, session) is None


def test_undated_previous_close_cannot_verify_band(scanner):
    scanner.refresh_circuit_limits(QuoteClient(120, 80, 110))
    assert scanner._states['AAA'].previous_close == 100
    assert not scanner.snapshot()['stocks'][0]['circuit_band_eligible']


@pytest.mark.parametrize('seconds', [121, 86400, -30])
def test_stale_previous_day_and_future_quote_cannot_pass(scanner, seconds):
    client = QuoteClient(120, 80, 110)
    client.item['net_change'] = 10
    scanner.refresh_circuit_limits(client)
    scanner._states['AAA'].circuit_fetched_at -= timedelta(seconds=seconds)
    row = scanner.snapshot()['stocks'][0]
    assert row['circuit_band_status'] == 'pending_or_stale'
    assert row['circuit_band_eligible'] is False
    assert row['circuit_reference_close'] is None


def test_known_fno_is_dynamic_and_quote_failure_clears_previous_verification(scanner):
    client = QuoteClient(120, 80, 110)
    client.item['net_change'] = 10
    state = scanner._states.pop('AAA')
    state.instrument.symbol = 'RELIANCE'
    scanner._states['RELIANCE'] = state
    scanner.refresh_circuit_limits(client)
    row = scanner.snapshot()['stocks'][0]
    assert row['circuit_band_status'] == 'dynamic' and not row['circuit_band_eligible']
    state.instrument.symbol = 'AAA'
    scanner._states = {'AAA': state}
    assert scanner.snapshot()['stocks'][0]['circuit_band_eligible']
    client.failure = 'DH-901'
    state.circuit_attempt_at -= timedelta(seconds=61)
    scanner.refresh_circuit_limits(client)
    row = scanner.snapshot()['stocks'][0]
    assert not row['circuit_band_eligible'] and row['circuit_reference_close'] is None
    assert row['possible_candidate']


def test_new_qualifier_gets_quote_without_refetching_old_qualifier(scanner):
    from app.dhan_scanner import StockState, Instrument
    client = QuoteClient(120, 80, 110)
    client.item['net_change'] = 10
    scanner.refresh_circuit_limits(client)
    scanner._states['RED'] = StockState(Instrument('RED', '456', 'RED'), redwala_gira=True,
        qualifies_scan=True, signal_session=datetime.now(IST).date())
    scanner.refresh_circuit_limits(client)
    assert client.calls == [{'NSE_EQ': [123]}, {'NSE_EQ': [456]}]
    assert all(row['circuit_band_eligible'] for row in scanner.snapshot()['stocks'])
