"""Dhan SDK adapter. Order submissions are deliberately never retried here."""
import asyncio
from datetime import datetime, timedelta
import json
import math
import threading
import time

from .dhan_scanner import IST
from .algo_feed import AlgoMarketFeed, fresh


def payload(response):
    if not isinstance(response, dict) or str(response.get('status', '')).lower() != 'success':
        raise RuntimeError(f'Dhan request failed: {response.get("remarks", "unknown response") if isinstance(response, dict) else "invalid response"}')
    return response.get('data')


def integer(value):
    number = float(value)
    if not math.isfinite(number) or number != int(number):
        raise ValueError('Broker quantity is not an integer')
    return int(number)


def trading_response(response, parse):
    # Dhan documents a successful cancellation as HTTP 202 with no body.
    # SDK 2.2.0 otherwise tries to JSON-decode it and reports failure.
    if response.status_code in (202, 204) and not response.content.strip():
        return {'status': 'success', 'data': None, 'remarks': ''}
    return parse(response)


class OrderSocket:
    """Official order-update wire protocol, without SDK 2.2's token print."""
    def __init__(self, client_id, token, notify):
        self.client_id, self.token, self.notify = client_id, token, notify
        self.stop = threading.Event()
        self.connected = False
        self.thread = threading.Thread(target=lambda: asyncio.run(self.run()), daemon=True, name='algo-order-updates')

    async def run(self):
        import websockets
        while not self.stop.is_set():
            try:
                async with websockets.connect('wss://api-order-update.dhan.co', open_timeout=10,
                                              close_timeout=2, ping_interval=20, ping_timeout=10) as ws:
                    await ws.send(json.dumps({'LoginReq': {'MsgCode': 42, 'ClientId': self.client_id,
                                                          'Token': self.token}, 'UserType': 'SELF'}))
                    self.connected = True
                    self.notify()
                    while not self.stop.is_set():
                        try:
                            message = json.loads(await asyncio.wait_for(ws.recv(), timeout=1))
                            if message.get('Type') == 'order_alert':
                                # REST trades/positions are authoritative. Updates wake reconciliation;
                                # duplicated/out-of-order socket messages never change filled quantity.
                                self.notify()
                        except asyncio.TimeoutError:
                            continue
            except Exception:
                self.connected = False
            finally:
                self.connected = False
            for _ in range(20):
                if self.stop.is_set():
                    return
                await asyncio.sleep(.1)


class DhanAlgoBroker:
    def __init__(self, engine, wake):
        self.engine, self.wake = engine, wake
        config = engine.store.load()
        self.account = config.client_id
        self._token = config.access_token
        self.client = engine._client()
        if hasattr(self.client, 'dhan_http'):
            self.client.dhan_http.timeout = 5
            parse = self.client.dhan_http._parse_response
            self.client.dhan_http._parse_response = lambda response: trading_response(response, parse)
        self.socket = None
        self.market_feed = None
        self._market_stop = threading.Event()
        self._fallback_thread = None
        self._market_age = 5
        self._quote_client = None
        self._lock = threading.Lock()
        self._last_call = 0

    def identity_ok(self):
        config = self.engine.store.load()
        return config.client_id == self.account and config.access_token == self._token

    def call(self, method, *args, **kwargs):
        # Conservative aggregate rate for order/portfolio reads and mutations.
        with self._lock:
            wait = .22 - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            return payload(method(*args, **kwargs))

    def connect_orders(self):
        if self.socket is None:
            self.socket = OrderSocket(self.account, self._token, self.wake)
            self.socket.thread.start()

    def close(self):
        if self.socket:
            self.socket.stop.set()
        self._market_stop.set()
        if self.market_feed:
            self.market_feed.stop.set()

    def connect_market(self, ids, on_tick, max_age=5):
        if self.market_feed is None:
            self.market_feed = AlgoMarketFeed(self.account, self._token, self.wake, on_tick)
            self.market_feed.subscribe(ids)
            self.market_feed.thread.start()
            self._fallback_thread = threading.Thread(target=self._quote_fallback,
                name='algo-quote-fallback', daemon=True)
            self._fallback_thread.start()
        self._market_age = max_age
        self.market_feed.subscribe(ids)

    def _quote_fallback(self):
        # A slow/shared-throttled quote never blocks the tick or order worker.
        while not self._market_stop.is_set():
            feed = self.market_feed
            now = datetime.now(IST)
            quotes = feed.quotes()
            with feed.lock:
                ids = list(feed.ids)
            missing = [sid for sid in ids if not fresh(quotes.get(sid), now, self._market_age)
                       or not fresh(quotes.get(sid), now, self._market_age, depth=True)]
            if missing and self.identity_ok():
                try:
                    for sid, quote in self.quotes(missing, now, self._market_age).items():
                        if not self._market_stop.is_set():
                            feed.accept(sid, quote)
                except Exception:
                    pass  # Stale/unavailable data is surfaced by the controller.
            self._market_stop.wait(1.05)

    def market_quotes(self):
        return self.market_feed.quotes() if self.market_feed else {}

    def positions(self):
        rows = self.call(self.client.get_positions)
        if not isinstance(rows, list):
            raise ValueError('Invalid broker positions response')
        return rows

    def orders(self):
        rows = self.call(self.client.get_order_list)
        if not isinstance(rows, list):
            raise ValueError('Invalid broker order book')
        return rows

    def order(self, intent):
        if intent.get('order_id'):
            row = self.call(self.client.get_order_by_id, intent['order_id'])
        else:
            row = self.call(self.client.get_order_by_correlationID, intent['correlation'])
        if not isinstance(row, dict) or not row.get('orderId'):
            raise ValueError('Order identity unresolved; no replacement will be submitted')
        return row

    def trades(self, order_id):
        rows = self.call(self.client.get_trade_book, order_id)
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise ValueError('Invalid broker trade book')
        return rows

    def submit(self, security_id, intent):
        # MARKET is a request, not a fill guarantee; Dhan price protection may
        # leave it pending. The controller handles partial/pending/rejected orders.
        return self.call(self.client.place_order, security_id=str(security_id), exchange_segment='NSE_EQ',
                         transaction_type='BUY' if intent['delta'] > 0 else 'SELL', quantity=abs(intent['delta']),
                         order_type='MARKET', product_type='INTRADAY', price=0, validity='DAY',
                         after_market_order=False, tag=intent['correlation'], should_slice=False)

    def cancel(self, order_id):
        return self.call(self.client.cancel_order, order_id)

    def quotes(self, security_ids, now, max_age=5):
        if self._quote_client is None:
            self._quote_client = self.engine._client()
            if hasattr(self._quote_client, 'dhan_http'):
                self._quote_client.dhan_http.timeout = 5
        started = time.monotonic()
        raw = payload(self.engine._quote_call(self._quote_client.quote_data, {'NSE_EQ': [int(sid) for sid in set(security_ids)]}))
        # Quote endpoint has its own envelope inside the SDK's envelope.
        if isinstance(raw, dict) and 'status' in raw:
            raw = payload(raw)
        received = now + timedelta(seconds=max(0, time.monotonic() - started))
        values = raw.get('NSE_EQ', {}) if isinstance(raw, dict) else {}
        result = {}
        for sid in security_ids:
            row = values.get(str(sid), values.get(int(sid), {}))
            try:
                raw_stamp = row.get('last_trade_time', '')
                stamp = None
                for fmt in ('%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S'):
                    try:
                        stamp = datetime.strptime(raw_stamp, fmt).replace(tzinfo=IST)
                        break
                    except (ValueError, TypeError):
                        pass
                if stamp is None or not -2 <= (received - stamp).total_seconds() <= max_age:
                    continue
                quote = {'time': stamp.isoformat(), 'depth_time': received.isoformat(),
                         'received_at': received.isoformat(), 'request_started_at': now.isoformat(), 'source': 'rest'}
                ltp = float(row.get('last_price', 0))
                if math.isfinite(ltp) and ltp > 0:
                    quote['ltp'] = ltp
                depth = row.get('depth') or {}
                bids = [float(item['price']) for item in depth.get('buy', [])
                        if float(item['quantity']) > 0 and math.isfinite(float(item['price'])) and float(item['price']) > 0]
                asks = [float(item['price']) for item in depth.get('sell', [])
                        if float(item['quantity']) > 0 and math.isfinite(float(item['price'])) and float(item['price']) > 0]
                if bids and asks and max(bids) <= min(asks):
                    quote.update(bid=max(bids), ask=min(asks))
                if 'ltp' in quote or 'bid' in quote:
                    result[str(sid)] = quote
            except (ValueError, TypeError, KeyError):
                continue
        return result


def position_qty(rows, security_id):
    return sum(integer(row['netQty']) for row in rows if str(row.get('securityId')) == str(security_id)
               and row.get('exchangeSegment') == 'NSE_EQ' and row.get('productType') == 'INTRADAY')


def same_instrument(row, security_id):
    return (str(row.get('securityId')) == str(security_id) and row.get('exchangeSegment') == 'NSE_EQ'
            and row.get('productType') == 'INTRADAY')
