from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo

import pytest
from dhanhq import DhanContext, dhanhq
from requests import Response

from app.dhan_scanner import Instrument, ScannerEngine, StockState
from app.schemas import StateOut
from app.storage import ConfigStore


IST = ZoneInfo("Asia/Kolkata")


class QuoteClient:
    def __init__(self, upper=101, lower=90, price=100):
        self.calls = []
        self.item = {"upper_circuit_limit": upper, "lower_circuit_limit": lower, "last_price": price}
        self.failure = None

    def quote_data(self, securities):
        self.calls.append(securities)
        if self.failure:
            return {"status": "failure", "remarks": {"error_code": self.failure}}
        return {"status": "success", "data": {
            segment: {str(sid): dict(self.item) for sid in ids}
            for segment, ids in securities.items()
        }}


@pytest.fixture
def scanner(tmp_path):
    engine = ScannerEngine(ConfigStore(tmp_path / "config.json"))
    engine._states = {"AAA": StockState(
        Instrument("AAA", "123", "AAA"), ltp=100, previous_close=100,
        possible_candidate=True, qualifies_scan=True, signal_session=datetime.now(IST).date(),
    )}
    return engine


def test_user_example_and_distances_update_from_websocket_without_quote_calls(scanner):
    client = QuoteClient()
    scanner.refresh_circuit_limits(client)
    row = StateOut(**scanner.snapshot()).stocks[0]
    assert row.upper_circuit_limit == 101
    assert row.lower_circuit_limit == 90
    assert row.upper_circuit_distance_percent == 1
    assert row.lower_circuit_distance_percent == 10
    assert row.circuit_error is None
    scanner._on_message(None, {"security_id": 123, "LTP": 100.5, "LTT": datetime.now(IST).strftime("%H:%M:%S")})
    row = scanner.snapshot()["stocks"][0]
    assert row["upper_circuit_distance_percent"] == pytest.approx(0.5 / 100.5 * 100)
    assert row["lower_circuit_distance_percent"] == pytest.approx(10.5 / 100.5 * 100)
    scanner.refresh_circuit_limits(client)
    assert len(client.calls) == 1


def test_installed_sdk_quote_envelope_is_unwrapped(scanner, monkeypatch):
    client = dhanhq(DhanContext("test-client", "test-token"))
    response = Response()
    response.status_code = 200
    response._content = json.dumps({"status": "success", "data": {"NSE_EQ": {"123": {
        "upper_circuit_limit": 101, "lower_circuit_limit": 90, "last_price": 100,
    }}}}).encode()

    def post(endpoint, payload):
        assert endpoint == "/marketfeed/quote"
        assert payload == {"NSE_EQ": [123]}
        return client.dhan_http._parse_response(response)

    monkeypatch.setattr(client.dhan_http, "post", post)
    scanner.refresh_circuit_limits(client)
    row = scanner.snapshot()["stocks"][0]
    assert row["circuit_error"] is None
    assert row["upper_circuit_distance_percent"] == 1
    assert row["lower_circuit_distance_percent"] == 10


@pytest.mark.parametrize("price,upper,lower", [(101, 0, 11 / 101 * 100), (90, 11 / 90 * 100, 0)])
def test_at_circuit_is_zero_not_missing(scanner, price, upper, lower):
    scanner.refresh_circuit_limits(QuoteClient(price=price))
    row = scanner.snapshot()["stocks"][0]
    assert row["upper_circuit_distance_percent"] == pytest.approx(upper)
    assert row["lower_circuit_distance_percent"] == pytest.approx(lower)


@pytest.mark.parametrize("upper,lower", [(None, None), (0, -1), (float("nan"), float("inf")), (90, 101)])
def test_invalid_limits_do_not_remove_candidate(scanner, upper, lower):
    scanner.refresh_circuit_limits(QuoteClient(upper, lower))
    row = scanner.snapshot()["stocks"][0]
    assert row["upper_circuit_distance_percent"] is None
    assert row["lower_circuit_distance_percent"] is None
    assert row["circuit_error"]
    assert row["possible_candidate"] is True
    assert row["qualifies_scan"] is True


def test_partial_limit_can_display_independently(scanner):
    scanner.refresh_circuit_limits(QuoteClient(lower=None))
    row = scanner.snapshot()["stocks"][0]
    assert row["upper_circuit_distance_percent"] == 1
    assert row["lower_circuit_distance_percent"] is None


@pytest.mark.parametrize("price", [0, None, float("nan"), 102, 89])
def test_bad_ltp_or_outside_band_does_not_give_misleading_distance(scanner, price):
    scanner.refresh_circuit_limits(QuoteClient())
    scanner._states["AAA"].ltp = price
    row = scanner.snapshot()["stocks"][0]
    assert row["upper_circuit_distance_percent"] is None
    assert row["lower_circuit_distance_percent"] is None


@pytest.mark.parametrize("age", [timedelta(seconds=121), timedelta(days=1)])
def test_expired_or_previous_date_limits_are_unavailable(scanner, age):
    scanner.refresh_circuit_limits(QuoteClient())
    scanner._states["AAA"].circuit_fetched_at -= age
    row = scanner.snapshot()["stocks"][0]
    assert row["upper_circuit_limit"] is None
    assert row["upper_circuit_distance_percent"] is None
    assert "stale" in row["circuit_error"]


def test_rate_limit_failure_and_later_recovery_preserve_badges(scanner):
    client = QuoteClient()
    client.failure = "DH-904"
    scanner.refresh_circuit_limits(client)
    scanner.refresh_circuit_limits(client)
    assert len(client.calls) == 1
    row = scanner.snapshot()["stocks"][0]
    assert "DH-904" in row["circuit_error"]
    assert row["possible_candidate"] is True
    assert row["error"] is None
    client.failure = None
    scanner._states["AAA"].circuit_attempt_at -= timedelta(seconds=61)
    scanner.refresh_circuit_limits(client)
    assert scanner.snapshot()["stocks"][0]["upper_circuit_distance_percent"] == 1


def test_batches_only_current_qualified_stocks_including_redwala(scanner):
    scanner._states["RED"] = StockState(Instrument("RED", "456", "RED"), qualifies_scan=True,
        redwala_gira=True, signal_session=datetime.now(IST).date())
    scanner._states["OTHER"] = StockState(Instrument("OTHER", "789", "OTHER"))
    scanner._states["OLD"] = StockState(Instrument("OLD", "999", "OLD"), qualifies_scan=True,
        signal_session=datetime.now(IST).date() - timedelta(days=1))
    client = QuoteClient()
    scanner.refresh_circuit_limits(client)
    assert client.calls == [{"NSE_EQ": [123, 456]}]


def test_quote_does_not_overwrite_a_newer_websocket_tick(scanner):
    client = QuoteClient()
    fetch = client.quote_data

    def racing_quote(securities):
        scanner._on_message(None, {"security_id": 123, "LTP": 100.5})
        return fetch(securities)

    client.quote_data = racing_quote
    scanner.refresh_circuit_limits(client)
    assert scanner._states["AAA"].ltp == 100.5


def test_removed_symbol_is_not_written_back_by_inflight_quote(scanner):
    client = QuoteClient()
    fetch = client.quote_data

    def replace_list(securities):
        scanner._states = {}
        return fetch(securities)

    client.quote_data = replace_list
    scanner.refresh_circuit_limits(client)
    assert scanner.snapshot()["stocks"] == []


def test_quote_batches_respect_1000_instrument_limit(scanner):
    scanner._states = {str(index): StockState(Instrument(str(index), str(index), str(index)),
        qualifies_scan=True, signal_session=datetime.now(IST).date()) for index in range(1001)}
    client = QuoteClient()
    scanner.refresh_circuit_limits(client)
    assert [len(call["NSE_EQ"]) for call in client.calls] == [1000, 1]


def test_polling_worker_stops_on_event(scanner, monkeypatch):
    calls = []
    monkeypatch.setattr(scanner, "refresh_circuit_limits", lambda: calls.append("refresh"))

    class StopEvent:
        def is_set(self):
            return False

        def wait(self, seconds):
            assert seconds == 60
            return True

    scanner._refresh_circuit_limits_loop(StopEvent())
    assert calls == ["refresh"]


def test_ohlc_and_circuit_quotes_share_throttle(scanner, monkeypatch):
    ticks = [100.0]
    sleeps = []
    monkeypatch.setattr("app.dhan_scanner.time.monotonic", lambda: ticks[0])

    def sleep(seconds):
        sleeps.append(seconds)
        ticks[0] += seconds

    monkeypatch.setattr("app.dhan_scanner.time.sleep", sleep)
    client = QuoteClient()
    client.ohlc_data = lambda _securities: {"status": "success", "data": {}}
    scanner._ohlc_batch_with_retry(client, {"NSE_EQ": [123]})
    scanner.refresh_circuit_limits(client)
    assert sleeps == [pytest.approx(1.05)]
