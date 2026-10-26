"""Selected-stock Dhan Full feed. No orders or disk I/O on the receive thread."""
import asyncio
from datetime import datetime
import json
import math
import struct
import threading
from urllib.parse import urlencode

from .dhan_scanner import IST


def fresh(quote, now, max_age=5, *, depth=False):
    if not quote:
        return False
    try:
        stamp = datetime.fromisoformat(quote['depth_time' if depth else 'time'])
        if not -2 <= (now - stamp).total_seconds() <= max_age:
            return False
        fields = ('bid', 'ask') if depth else ('ltp',)
        if not all(math.isfinite(float(quote[k])) and float(quote[k]) > 0 for k in fields):
            return False
        return not depth or quote['bid'] <= quote['ask']
    except (KeyError, TypeError, ValueError):
        return False


class AlgoMarketFeed:
    def __init__(self, client_id, token, notify, on_tick):
        self.client_id, self.token = client_id, token
        self.notify, self.on_tick = notify, on_tick
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.ids = set()
        self.latest = {}
        self.connected = False
        self.message = 'Waiting for market feed'
        self.thread = threading.Thread(target=lambda: asyncio.run(self.run()),
                                       name='algo-market-feed', daemon=True)

    def subscribe(self, ids):
        with self.lock:
            self.ids = set(map(str, ids))
            self.latest = {sid: q for sid, q in self.latest.items() if sid in self.ids}

    def quotes(self):
        with self.lock:
            return {sid: dict(q) for sid, q in self.latest.items()}

    def accept(self, sid, quote):
        sid = str(sid)
        with self.lock:
            if sid not in self.ids:
                return
            prior = self.latest.get(sid)
            if prior and quote['time'] < prior['time']:
                return
            # Do not let an older REST response overwrite newly received depth.
            if prior and quote.get('request_started_at', quote.get('received_at', '')) < prior.get('received_at', ''):
                return
            self.latest[sid] = dict(quote)
        self.on_tick(sid, quote)
        self.notify()

    def receive(self, data, now=None):
        now = now or datetime.now(IST)
        if not isinstance(data, bytes):
            return
        offset = 0
        while offset + 8 <= len(data):
            code, size, segment, sid = struct.unpack_from('<BHBI', data, offset)
            if size < 8 or offset + size > len(data):
                raise ValueError('Malformed market feed packet')
            packet = data[offset:offset + size]
            offset += size
            if code == 50:
                reason = struct.unpack_from('<H', packet, 8)[0] if size >= 10 else 0
                self.message = f'Market feed disconnected (code {reason}); reconnecting'
                raise ConnectionError('Market feed disconnected')
            if code != 8 or segment != 1:
                continue
            if size != 162:
                raise ValueError('Invalid Full packet length')
            ltp = round(struct.unpack_from('<f', packet, 8)[0], 2)
            epoch = struct.unpack_from('<I', packet, 14)[0]
            stamp = datetime.fromtimestamp(epoch, IST)
            quote = {'ltp': ltp, 'time': stamp.isoformat(), 'source': 'websocket',
                     'received_at': now.isoformat(), 'depth_time': now.isoformat()}
            if not fresh(quote, now, 30):
                continue
            bids, asks = [], []
            for n in range(5):
                bq, aq, _, _, bid, ask = struct.unpack_from('<IIHHff', packet, 62 + 20*n)
                if bq and math.isfinite(bid) and bid > 0:
                    bids.append(round(bid, 2))
                if aq and math.isfinite(ask) and ask > 0:
                    asks.append(round(ask, 2))
            if bids and asks and max(bids) <= min(asks):
                quote.update(bid=max(bids), ask=min(asks))
            self.accept(sid, quote)

    async def run(self):
        import websockets
        url = 'wss://api-feed.dhan.co?' + urlencode(dict(version=2, token=self.token,
                                                        clientId=self.client_id, authType=2))
        delay = 1
        while not self.stop.is_set():
            with self.lock:
                wanted = set(self.ids)
            if not wanted:
                await asyncio.sleep(.1)
                continue
            try:
                async with websockets.connect(url, open_timeout=10, close_timeout=2,
                                              ping_interval=20, ping_timeout=10) as ws:
                    subscribed = set()
                    self.connected = True
                    self.message = 'Market websocket connected'
                    self.notify()
                    while not self.stop.is_set():
                        with self.lock:
                            wanted = set(self.ids)
                        if not wanted:
                            break
                        for code, ids in ((22, subscribed - wanted), (21, wanted - subscribed)):
                            ids = sorted(ids)
                            for i in range(0, len(ids), 100):
                                batch = ids[i:i+100]
                                await ws.send(json.dumps({'RequestCode': code, 'InstrumentCount': len(batch),
                                    'InstrumentList': [{'ExchangeSegment': 'NSE_EQ', 'SecurityId': sid} for sid in batch]}))
                        subscribed = wanted
                        try:
                            self.receive(await asyncio.wait_for(ws.recv(), timeout=.1))
                            delay = 1
                        except asyncio.TimeoutError:
                            continue
            except Exception:
                # Never log an exception containing the token-bearing URL.
                if not self.message.startswith('Market feed disconnected'):
                    self.message = 'Market websocket unavailable; reconnecting, REST fallback active'
            finally:
                self.connected = False
                with self.lock:
                    self.latest.clear()
                self.notify()
            for _ in range(delay * 10):
                if self.stop.is_set():
                    return
                await asyncio.sleep(.1)
            delay = min(delay * 2, 30)
