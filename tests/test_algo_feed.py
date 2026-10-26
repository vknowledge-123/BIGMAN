"""Wire packets, reconnect/subscriptions and fallback: no real network/orders."""
import asyncio
from datetime import datetime, timedelta
import json
import struct

import pytest

from app.algo_feed import AlgoMarketFeed, fresh
from app.dhan_scanner import IST

NOW = datetime(2026, 10, 16, 10, 0, tzinfo=IST)


def packet(price=100, stamp=NOW, sid=1, bid=99.95, ask=100.05, depth=True):
    raw = bytearray(162)
    struct.pack_into('<BHBI', raw, 0, 8, 162, 1, sid)
    struct.pack_into('<f', raw, 8, price)
    struct.pack_into('<I', raw, 14, int(stamp.timestamp()))
    if depth:
        struct.pack_into('<IIHHff', raw, 62, 10, 20, 1, 1, bid, ask)
    return bytes(raw)


def feed():
    events = []
    f = AlgoMarketFeed('TEST', 'FAKE', lambda: None, lambda sid, q: events.append((sid, q)))
    f.subscribe(['1'])
    return f, events


def test_full_feed_parses_ltp_and_best_depth_including_joined_packets():
    f, events = feed()
    f.receive(packet()+packet(101, bid=100.95, ask=101.05), NOW)
    assert len(events) == 2
    q = f.quotes()['1']
    assert (q['ltp'], q['bid'], q['ask']) == (101, 100.95, 101.05)
    assert fresh(q, NOW) and fresh(q, NOW, depth=True)


def test_older_stale_unknown_invalid_packets_rejected():
    f, events = feed()
    f.receive(packet(), NOW)
    f.receive(packet(98, NOW-timedelta(seconds=1)), NOW)
    f.receive(packet(98, NOW-timedelta(seconds=40)), NOW)
    f.receive(packet(98, NOW+timedelta(seconds=10)), NOW)
    f.receive(packet(float('nan')), NOW)
    f.receive(packet(sid=2), NOW)
    assert len(events) == 1
    with pytest.raises(ValueError):
        f.receive(packet()[:-1], NOW)


@pytest.mark.parametrize('kwargs', [{'depth': False}, {'bid': 102, 'ask': 101}])
def test_ltp_still_delivered_without_valid_depth(kwargs):
    f, events = feed()
    f.receive(packet(99, **kwargs), NOW)
    assert len(events) == 1
    assert fresh(events[0][1], NOW)
    assert not fresh(events[0][1], NOW, depth=True)


def test_older_rest_response_cannot_replace_newer_websocket_tick():
    f, events = feed()
    f.receive(packet(101), NOW)
    q = dict(f.quotes()['1'], source='rest', ltp=99,
             received_at=(NOW-timedelta(seconds=1)).isoformat())
    f.accept('1', q)
    assert f.quotes()['1']['ltp'] == 101 and len(events) == 1
    f.subscribe([])
    assert not f.quotes()


def test_full_subscription_and_dynamic_unsubscribe_without_scanner(monkeypatch):
    f, events = feed()
    sent = []
    class WS:
        count = 0
        async def send(self, data): sent.append(json.loads(data))
        async def recv(self):
            self.count += 1
            if self.count == 1:
                f.subscribe(['2'])
                return b''
            f.stop.set()
            return b''
    class Connection:
        async def __aenter__(self): return WS()
        async def __aexit__(self, *args): pass
    monkeypatch.setattr('websockets.connect', lambda *args, **kwargs: Connection())
    asyncio.run(f.run())
    assert [(m['RequestCode'], m['InstrumentList'][0]['SecurityId']) for m in sent] == [(21, '1'), (22, '1'), (21, '2')]
    assert not f.connected


def test_subscription_batches_respect_100_instrument_limit(monkeypatch):
    f, _ = feed()
    f.subscribe(map(str, range(205)))
    sent = []
    class WS:
        async def send(self, data): sent.append(json.loads(data))
        async def recv(self):
            f.stop.set()
            return b''
    class Connection:
        async def __aenter__(self): return WS()
        async def __aexit__(self, *args): pass
    monkeypatch.setattr('websockets.connect', lambda *args, **kwargs: Connection())
    asyncio.run(f.run())
    assert [r['InstrumentCount'] for r in sent] == [100, 100, 5]


def test_disconnect_packet_is_not_a_price_and_marks_reason():
    f, events = feed()
    with pytest.raises(ConnectionError):
        f.receive(struct.pack('<BHBIH', 50, 10, 1, 0, 807), NOW)
    assert '807' in f.message and not events


def test_reconnect_clears_depth_and_resubscribes_without_exposing_token(monkeypatch):
    f, _ = feed()
    connections, sent, waits = [], [], []
    class WS:
        async def send(self, data): sent.append(json.loads(data))
        async def recv(self):
            if len(connections) == 1:
                f.latest['1'] = {'invalid_old_snapshot': True}
                raise ConnectionError('connection with secret FAKE failed')
            f.stop.set()
            return b''
    class Connection:
        async def __aenter__(self):
            connections.append(1)
            if len(connections) == 2:
                assert not f.latest
                assert 'FAKE' not in f.message
            return WS()
        async def __aexit__(self, *args): pass
    async def sleep(seconds): waits.append(seconds)
    monkeypatch.setattr('websockets.connect', lambda *args, **kwargs: Connection())
    monkeypatch.setattr(asyncio, 'sleep', sleep)
    asyncio.run(f.run())
    assert len(connections) == 2 and len(waits) == 10
    assert [r['RequestCode'] for r in sent] == [21, 21]
    assert not f.connected
