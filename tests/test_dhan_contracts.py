"""Real installed SDK + documented HTTP bodies; all network transport replaced."""
import json
from datetime import timedelta
from urllib.parse import urlsplit

import pytest
import requests

from app.algo_broker import DhanAlgoBroker
from test_algo import env, start, tick, NOW


def response(body, status=200):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body).encode() if body is not None else b''
    return r


def test_sdk_quote_nested_envelope_and_ltp_without_depth(env, monkeypatch):
    service, _ = env
    calls = []
    stamp = NOW.strftime('%d/%m/%Y %H:%M:%S')
    def transport(self, method, url, **kwargs):
        calls.append((method, urlsplit(url).path, json.loads(kwargs['data'])))
        return response({'status': 'success', 'data': {'NSE_EQ': {
            '1': {'last_price': 100, 'last_trade_time': stamp, 'depth': {
                'buy': [{'price': 99.95, 'quantity': 10}], 'sell': [{'price': 100.05, 'quantity': 20}]}},
            '2': {'last_price': 99, 'last_trade_time': stamp, 'depth': {'buy': [], 'sell': []}}
        }}})
    monkeypatch.setattr(requests.Session, 'request', transport)
    broker = DhanAlgoBroker(service.engine, lambda: None)
    quotes = broker.quotes(['1', '2'], NOW)
    assert quotes['1']['bid'] == 99.95 and quotes['1']['ltp'] == 100
    assert quotes['2']['ltp'] == 99 and 'bid' not in quotes['2']
    assert calls[0][:2] == ('POST', '/v2/marketfeed/quote')
    assert sorted(calls[0][2]['NSE_EQ']) == [1, 2]


def test_sdk_quote_inner_failure_is_not_empty_success(env, monkeypatch):
    service, _ = env
    monkeypatch.setattr(requests.Session, 'request', lambda *a, **k:
        response({'status': 'failure', 'remarks': 'DH-904', 'data': {}}))
    broker = DhanAlgoBroker(service.engine, lambda: None)
    with pytest.raises(RuntimeError, match='DH-904'):
        broker.quotes(['1'], NOW)


def test_sdk_order_body_and_documented_empty_cancel_response(env, monkeypatch):
    service, _ = env
    calls = []
    def transport(self, method, url, **kwargs):
        path = urlsplit(url).path
        calls.append((method, path, json.loads(kwargs['data']) if kwargs.get('data') else None))
        if method == 'POST':
            return response({'orderId': 'D1', 'orderStatus': 'TRANSIT'})
        if method == 'DELETE':
            return response(None, 202)
        pytest.fail('Unexpected HTTP operation')
    monkeypatch.setattr(requests.Session, 'request', transport)
    broker = DhanAlgoBroker(service.engine, lambda: None)
    result = broker.submit('1', {'delta': -1000, 'correlation': 'alg-fixture'})
    assert result['orderId'] == 'D1'
    body = calls[0][2]
    assert (body['quantity'], body['transactionType'], body['orderType'], body['productType']) == (1000, 'SELL', 'MARKET', 'INTRADAY')
    assert body['dhanClientId'] == 'TEST' and body['correlationId'] == 'alg-fixture'
    assert body['price'] == 0 and body['afterMarketOrder'] is False
    assert broker.cancel('D1') is None
    assert calls[-1] == ('DELETE', '/v2/orders/D1', None)


@pytest.mark.parametrize('kind', ['order_id', 'account', 'missing_tag', 'null_trade_id', 'trade_account'])
def test_broker_identity_mismatch_never_applies_fills(env, kind):
    service, broker = env
    record = start(env)
    service.step(record, broker, tick())
    broker.fill(record['pending'], 500, 'TRADED')
    if kind == 'order_id': broker.order_row['orderId'] = 'OTHER'
    if kind == 'account': broker.order_row['dhanClientId'] = 'OTHER'
    if kind == 'missing_tag':
        record['pending']['order_id'] = None
        broker.order_row.pop('correlationId')
    if kind == 'null_trade_id': broker.trade_rows[0]['exchangeTradeId'] = None
    if kind == 'trade_account': broker.trade_rows[0]['dhanClientId'] = 'OTHER'
    with pytest.raises(RuntimeError):
        service.step(record, broker, tick())
    assert record['strategy']['net_qty'] == 0
    assert record['pending'] and len(broker.sent) == 1
