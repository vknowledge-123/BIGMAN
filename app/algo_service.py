"""Selected-stock paper/live controller, isolated from scanner lifecycle."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, time, timedelta
import threading
import time as clock
from uuid import uuid4

from . import dhan_scanner as market
from .algo_broker import DhanAlgoBroker, integer, position_qty, same_instrument
from .algo_feed import fresh
from .algo_journal import Journal
from .algo_strategy import AlgoSettings, Ladder, paper_execute, replay

TERMINAL = {'TRADED', 'CANCELLED', 'REJECTED', 'EXPIRED'}


class AlgoService:
    def __init__(self, engine):
        self.engine = engine
        self.journal = Journal(engine.store.path.parent / 'algo.sqlite3')
        self.lock = threading.RLock()
        self.records = {row['id']: row for row in self.journal.load()}
        for row in self.records.values():
            if row['status'] != 'done':
                row['status'] = 'paused'
                row['message'] = 'Application restarted. Reconcile and resume explicitly; no automatic entry.'
        self.broker = None
        self.broker_factory = DhanAlgoBroker
        self.wake = threading.Event()
        self.stop_event = threading.Event()
        self.thread = None
        self.settings = AlgoSettings.model_validate(self.journal.settings())
        self.observations = {}

    def now(self):
        return market.datetime.now(market.IST)

    def save_settings(self, settings):
        self.journal.settings(settings.model_dump())
        self.settings = settings

    def snapshot(self):
        with self.lock:
            rows = deepcopy(list(self.records.values()))
        rows.sort(key=lambda row: row['created_at'], reverse=True)
        return {'settings': self.settings.model_dump(), 'sessions': rows,
                'order_socket_connected': bool(self.broker and self.broker.socket and self.broker.socket.connected),
                'market_socket_connected': bool(self.broker and getattr(self.broker, 'market_feed', None)
                                                and self.broker.market_feed.connected)}

    @staticmethod
    def _generation(record):
        s = record['strategy']
        return (len(s['fills']), s['net_qty'], s['original'],
                (record.get('pending') or {}).get('correlation'), record['status'] == 'paused')

    def on_tick(self, security_id, quote):
        """Evaluate every accepted LTP without waiting for REST/disk operations.

        Latch the first exit/reversal. A later recovery cannot erase a trigger.
        Observations belong to an exact fill generation, never a new position.
        """
        now = self.now()
        with self.lock:
            for record in self.records.values():
                if (str(record['security_id']) != str(security_id) or record['status'] == 'done'
                        or record['session_date'] != now.date().isoformat()
                        or (record['status'] == 'paused' and not record.get('pending'))):
                    continue
                settings = record['strategy']['settings']
                if not fresh(quote, now, settings['max_quote_age_seconds']):
                    continue
                if not time(9, 15) <= now.time() < time(15, 30):
                    continue
                key = self._generation(record)
                obs = self.observations.get(record['id'])
                if obs is None or obs['key'] != key:
                    prior_cancel = bool(obs and record.get('pending') and obs['key'][3] == key[3]
                                        and obs.get('cancel'))
                    prior_reason = obs.get('cancel_reason') if prior_cancel else None
                    obs = {'key': key, 'strategy': Ladder(**deepcopy(record['strategy'])),
                           'trigger': deepcopy(record.get('trigger')), 'cancel': prior_cancel,
                           'cancel_reason': prior_reason}
                    self.observations[record['id']] = obs
                s = obs['strategy']
                obs['quote'] = dict(quote)
                if not s.started or not s.net_qty:
                    continue
                pending = record.get('pending')
                if pending:
                    # Never issue another order while actual filled quantity is unresolved.
                    if (pending['reason'] in {'entry', 'add'} or
                            (pending['reason'] == 'reverse' and s.net_qty * pending['desired'] > 0)):
                        action = s.action(quote['ltp'])
                        if action and action['reason'] in {'stop', 'reverse', 'target', 'max_loss'}:
                            obs['cancel'] = True
                            if obs.get('cancel_reason') not in {'target', 'max_loss'}:
                                obs['cancel_reason'] = action['reason']
                    continue
                if obs['trigger'] and obs['trigger']['reason'] != 'add':
                    continue
                action = s.action(quote['ltp'], entry_price=quote.get('ask' if s.side > 0 else 'bid'))
                if action:
                    obs['trigger'] = {**action, 'signal_price': quote['ltp'],
                                      'signal_at': now.isoformat(), 'signal_source': quote.get('source', 'websocket')}
        self.wake.set()

    def _observed(self, record, strategy):
        with self.lock:
            obs = self.observations.get(record['id'])
            if (obs and record.get('pending') and obs['key'][3] == record['pending']['correlation']
                    and obs.get('cancel')):
                record['pending']['risk_cancel'] = True
                if obs.get('cancel_reason') in {'target', 'max_loss'}:
                    strategy.day_locked = True
            if obs and obs['key'] == self._generation(record):
                observed = obs['strategy']
                # Merge only risk observations. Never replace authoritative fills,
                # capital sizing or a day lock set by the execution worker.
                if strategy.net_qty:
                    choose = max if strategy.side > 0 else min
                    strategy.best = choose(strategy.best, observed.best)
                    stops = [p for p in (strategy.stop, observed.stop) if p > 0]
                    if stops:
                        strategy.stop = choose(stops)
                strategy.day_locked = strategy.day_locked or observed.day_locked
                if obs.get('trigger') and (not record.get('trigger') or record['trigger']['reason'] == 'add'):
                    record['trigger'] = deepcopy(obs['trigger'])
                if record.get('pending') and obs.get('cancel'):
                    record['pending']['risk_cancel'] = True
            return strategy

    def _save(self, record, event=None):
        with self.lock:
            current = self.records.get(record['id'], {})
            # A click during a broker round trip must not be overwritten.
            record['exit_requested'] = bool(record.get('exit_requested') or current.get('exit_requested'))
            record['resume_requested'] = bool(record.get('resume_requested') or current.get('resume_requested'))
            self.journal.save(record, event)
            self.records[record['id']] = deepcopy(record)

    def _launch(self):
        self.journal.acquire()
        if not self.thread or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, name='selected-stock-algos', daemon=True)
            self.thread.start()
        self.wake.set()

    def start(self, request):
        now = self.now()
        settings = request.settings
        if not time(9, 16) <= now.time() < time.fromisoformat(settings.square_off):
            raise ValueError('Start Algo is available from 09:16 IST until its configured square-off time')
        symbol = request.symbol.strip().upper()
        with self.engine._lock:
            state = self.engine._states.get(symbol)
            eligible = state and state.signal_session == now.date() and state.confirmation_status == 'confirmed'
            if not eligible or not (state.possible_candidate if request.setup == 'possible' else state.redwala_gira):
                raise ValueError('Select a confirmed Possible Candidate or Redwala from today’s scan')
            instrument = state.instrument
        config = self.engine.store.load()
        if not config.client_id or not config.access_token:
            raise ValueError('Save Dhan credentials for live bid/ask data')
        self.journal.acquire()
        with self.lock:
            # Reload under execution ownership to catch records from a previous owner.
            for row in self.journal.load():
                if row['id'] not in self.records:
                    if row['status'] != 'done':
                        row['status'] = 'paused'
                        row['message'] = 'Previous process session loaded. Reconcile and resume explicitly.'
                    self.records[row['id']] = row
            for row in self.records.values():
                if row['symbol'] == symbol and row['mode'] == settings.mode and row['account'] == config.client_id:
                    if row['status'] != 'done':
                        raise ValueError('This stock already has an algo; reconcile or exit the existing session')
                    if row['session_date'] == now.date().isoformat() and row['strategy']['day_locked']:
                        raise ValueError('This stock is locked for the day after a target or maximum-loss exit')
            record = {'id': uuid4().hex, 'symbol': symbol, 'security_id': instrument.security_id,
                      'setup': request.setup, 'mode': settings.mode, 'account': config.client_id,
                      'session_date': now.date().isoformat(), 'created_at': now.isoformat(),
                      'status': 'queued', 'message': 'Waiting for fresh bid/ask and preflight checks',
                      'strategy': asdict(Ladder(settings.model_dump(), settings.side_for_setup(request.setup), settings.quantity)),
                      'pending': None, 'orders': [], 'exit_requested': False, 'resume_requested': False,
                      'broker_qty': None, 'quote': None, 'last_reconciled': None}
            self._save(record, {'event': 'selected_stock_start', 'mode': settings.mode})
            self._launch()
        return record['id']

    def command(self, session_id, action):
        self.journal.acquire()
        with self.lock:
            if session_id not in self.records:
                raise ValueError('Algo session not found')
            row = deepcopy(self.records[session_id])
            if row['status'] == 'done':
                return
            if action == 'exit':
                row['exit_requested'] = True
                row['message'] = 'Exit requested; cancel pending remainder, reconcile, then flatten this algo only'
            elif action == 'resume':
                row['resume_requested'] = True
                row['message'] = 'Reconciliation requested before resuming'
            else:
                raise ValueError('Unknown algo action')
            self._save(row, {'event': action})
            self._launch()

    def _get_broker(self):
        if self.broker is None:
            self.broker = self.broker_factory(self.engine, self.wake.set)
        if not self.broker.identity_ok():
            raise RuntimeError('Dhan account/token changed. Restore the original credentials or restart and reconcile.')
        return self.broker

    def _position_check(self, record, strategy, broker):
        actual = position_qty(broker.positions(), record['security_id'])
        record['broker_qty'] = actual
        record['last_reconciled'] = self.now().isoformat()
        if actual != strategy.net_qty:
            raise RuntimeError(f'Reconciliation required: broker quantity {actual}, app quantity {strategy.net_qty}. No new order sent.')

    def _preflight(self, record, strategy, broker):
        if record['account'] != broker.account:
            raise RuntimeError('Algo belongs to another Dhan account')
        self._position_check(record, strategy, broker)
        owned = {item.get('order_id') for item in record['orders']}
        if record.get('pending'):
            owned.add(record['pending'].get('order_id'))
        for order in broker.orders():
            if same_instrument(order, record['security_id']) and str(order.get('orderStatus', '')).upper() not in TERMINAL:
                if str(order.get('orderId')) not in owned:
                    raise RuntimeError('An external pending intraday order exists for this stock; resolve it before running the algo')

    def _submit(self, record, strategy, action, broker, quote):
        if self.stop_event.is_set():
            return
        delta = action['desired'] - strategy.net_qty
        if not delta:
            return
        if record['mode'] == 'paper':
            paper_execute(strategy, action, quote['bid'], quote['ask'], self.now().isoformat())
            record['strategy'] = asdict(strategy)
            record['pnl'] = strategy.mark(quote['bid'] if strategy.net_qty >= 0 else quote['ask'])
            record['status'] = 'done' if strategy.done else 'running'
            record['message'] = f'Paper {action["reason"]} filled'
            record['trigger'] = None
            self._save(record, {'event': 'paper_fill', **action})
            return
        self._preflight(record, strategy, broker)
        # Ticks continue during REST preflight. An exit supersedes a queued add.
        strategy = self._observed(record, strategy)
        newer = record.get('trigger')
        if action['reason'] == 'add' and newer and newer['reason'] != 'add':
            action = newer
        if hasattr(broker, 'market_quotes'):
            latest = broker.market_quotes().get(str(record['security_id']))
            if latest and fresh(latest, self.now(), strategy.config.max_quote_age_seconds, depth=True):
                quote = latest
        if not broker.identity_ok():
            raise RuntimeError('Dhan credentials changed during preflight; no order sent. Reconcile before resuming.')
        if action['desired'] != 0 and self.now().time() >= time.fromisoformat(strategy.config.square_off):
            if not strategy.net_qty:
                strategy.done = True
                record.update(status='done', message='Square-off reached during broker checks; no entry sent',
                              strategy=asdict(strategy), trigger=None)
                self._save(record)
                return
            action = {'desired': 0, 'reason': 'square_off'}
        if action['desired'] != 0 and (not broker.socket or not broker.socket.connected):
            record['message'] = 'Waiting for the order-update socket; new submissions blocked'
            self._save(record)
            return
        with self.lock:
            if self.records[record['id']].get('exit_requested') and action['desired'] != 0:
                return
        if action['desired'] != 0:
            valid_quote = bool(quote)
            if quote:
                age = (self.now() - datetime.fromisoformat(quote['time'])).total_seconds()
                valid_quote = -2 <= age <= strategy.config.max_quote_age_seconds
                if quote.get('source'):
                    valid_quote = valid_quote and fresh(quote, self.now(), strategy.config.max_quote_age_seconds, depth=True)
            if not valid_quote:
                record['message'] = 'Quote became stale during broker checks; waiting for fresh data'
                self._save(record)
                return
        if action['reason'] == 'entry' and strategy.config.sizing == 'capital':
            strategy.base_qty = int(strategy.config.capital / quote['ask' if strategy.initial_side > 0 else 'bid'])
            if strategy.base_qty < 1:
                raise ValueError('Capital is too small for one share')
            action = {**action, 'desired': strategy.initial_side * strategy.base_qty}
        elif action['reason'] == 'add' and strategy.config.sizing == 'capital':
            size = int(strategy.config.capital / quote['ask' if strategy.side > 0 else 'bid'])
            if size < 1:
                return
            action = {**action, 'desired': strategy.net_qty + strategy.side * size}
        delta = action['desired'] - strategy.net_qty
        intent = {**action, 'delta': delta, 'correlation': 'alg-' + uuid4().hex[:24],
                  'order_id': None, 'created_at': self.now().isoformat(), 'filled_qty': 0,
                  'applied': {}, 'cancel_requested': False, 'state': 'SUBMITTING'}
        record['pending'] = intent
        record['trigger'] = None
        record['strategy'] = asdict(strategy)
        self._save(record, {'event': 'intent_before_submission', 'intent': intent})
        with self.lock:
            cutoff_before_send = action['desired'] != 0 and self.now().time() >= time.fromisoformat(strategy.config.square_off)
            cancelled_before_send = (self.stop_event.is_set() or cutoff_before_send
                                    or (self.records[record['id']].get('exit_requested') and action['desired'] != 0))
        if cancelled_before_send:
            record['pending'] = None
            record['status'] = 'paused'
            record['message'] = 'Stopped before order submission; no order sent'
            if cutoff_before_send:
                record['exit_requested'] = bool(strategy.net_qty)
            self._save(record, {'event': 'intent_not_sent', 'correlation': intent['correlation']})
            return
        try:
            result = broker.submit(record['security_id'], intent)
            if not isinstance(result, dict) or not result.get('orderId'):
                raise RuntimeError('No order ID in acknowledgement')
            intent['order_id'] = str(result['orderId'])
            intent['state'] = str(result.get('orderStatus', 'PENDING')).upper()
            record['message'] = f'{action["reason"]} submitted; awaiting reconciled fills'
        except Exception as exc:
            intent['state'] = 'UNCERTAIN'
            record['message'] = f'Submission uncertain: {exc}. Looking up correlation ID; never automatically resubmitting.'
        self._save(record, {'event': 'submission_response', 'correlation': intent['correlation']})

    def _reconcile_order(self, record, strategy, broker, quote):
        intent = record['pending']
        order = broker.order(intent)
        expected_id = intent.get('order_id')
        if ((expected_id and str(order.get('orderId')) != str(expected_id))
                or (not expected_id and order.get('correlationId') != intent['correlation'])
                or (order.get('dhanClientId') and str(order['dhanClientId']) != record['account'])):
            raise RuntimeError('Broker order identity does not match the saved intent/account')
        if (not same_instrument(order, record['security_id'])
                or str(order.get('transactionType')).upper() != ('BUY' if intent['delta'] > 0 else 'SELL')
                or integer(order['quantity']) != abs(intent['delta'])
                or (order.get('correlationId') and order['correlationId'] != intent['correlation'])):
            raise RuntimeError('Broker order identity or quantity does not match the saved intent')
        intent['order_id'] = str(order['orderId'])
        trades = broker.trades(intent['order_id'])
        signed = 1 if intent['delta'] > 0 else -1
        for trade in trades:
            if str(trade.get('orderId')) != intent['order_id'] or not same_instrument(trade, record['security_id']):
                raise RuntimeError('Trade book contains a different instrument/order')
            if str(trade.get('transactionType', '')).upper() != ('BUY' if signed > 0 else 'SELL'):
                raise RuntimeError('Trade direction does not match the saved order')
            if trade.get('dhanClientId') and str(trade['dhanClientId']) != record['account']:
                raise RuntimeError('Trade book account does not match the saved session')
            raw_trade_id = trade.get('exchangeTradeId')
            if raw_trade_id is None or not str(raw_trade_id).strip():
                raise RuntimeError('Trade has no exchange trade ID; cannot safely deduplicate')
            trade_id = str(raw_trade_id)
            qty, price = integer(trade['tradedQuantity']), float(trade['tradedPrice'])
            if qty <= 0:
                raise RuntimeError('Invalid trade quantity')
            value = {'qty': qty, 'price': price}
            if trade_id in intent['applied']:
                if intent['applied'][trade_id] != value:
                    raise RuntimeError('Previously applied trade was changed by broker')
                continue
            if sum(row['qty'] for row in intent['applied'].values()) + qty > abs(intent['delta']):
                raise RuntimeError('Fills exceed submitted quantity')
            strategy.fill(signed * qty, price, trade.get('exchangeTime', self.now().isoformat()), intent['order_id'] + ':' + trade_id)
            intent['applied'][trade_id] = value
            record['strategy'] = asdict(strategy)
            self._save(record, {'event': 'broker_fill', 'order_id': intent['order_id'], 'trade_id': trade_id, **value})
        filled = sum(row['qty'] for row in intent['applied'].values())
        intent['filled_qty'] = filled
        reported = integer(order.get('filledQty', 0))
        intent['state'] = str(order['orderStatus']).upper()
        if reported != filled:
            record['message'] = 'Order/trade book disagree temporarily; waiting for reconciliation'
            self._save(record)
            return
        elapsed = (self.now() - datetime.fromisoformat(intent['created_at'])).total_seconds()
        strategy = self._observed(record, strategy)
        risk_hit = intent.get('risk_cancel', False)
        if quote and strategy.net_qty and (intent['reason'] in {'entry', 'add'} or
                (intent['reason'] == 'reverse' and strategy.net_qty * intent['desired'] > 0)):
            price = quote.get('ltp') or (quote['bid'] if strategy.net_qty > 0 else quote['ask'])
            risk_action = strategy.action(price)
            risk_hit = risk_hit or bool(risk_action and risk_action['reason'] in {'stop', 'reverse', 'target', 'max_loss'})
            intent['risk_cancel'] = risk_hit
        if intent['state'] not in TERMINAL:
            cutoff = self.now().time() >= time.fromisoformat(strategy.config.square_off)
            if record['exit_requested'] or risk_hit or cutoff or elapsed >= strategy.config.order_timeout_seconds:
                last_cancel = datetime.fromisoformat(intent.get('last_cancel_at', intent['created_at']))
                if (not intent['cancel_requested'] or (self.now() - last_cancel).total_seconds() >= 5) and intent.get('cancel_attempts', 0) < 3:
                    intent['cancel_requested'] = True
                    intent['cancel_attempts'] = intent.get('cancel_attempts', 0) + 1
                    intent['last_cancel_at'] = self.now().isoformat()
                    self._save(record, {'event': 'cancel_requested', 'order_id': intent['order_id']})
                    broker.cancel(intent['order_id'])
                record['message'] = 'Awaiting final cancellation/fills before any replacement or exit'
                if intent.get('cancel_attempts', 0) >= 3:
                    record['message'] += '; cancellation limit reached. Check/cancel the order in Dhan; reconciliation continues.'
            record['strategy'] = asdict(strategy)
            self._save(record)
            return
        self._position_check(record, strategy, broker)
        average = sum(row['qty'] * row['price'] for row in intent['applied'].values()) / filled if filled else 0
        if filled == abs(intent['delta']) and intent['state'] == 'TRADED':
            strategy.completed({**intent, 'average_fill': average})
            if intent.get('risk_cancel') and strategy.net_qty:
                record['exit_requested'] = True
                record['message'] = 'Risk threshold touched during partial fills; closing reconciled exposure'
        else:
            # A partial terminal entry/add/reversal does not start another ladder.
            # Flatten only the actual, reconciled app exposure.
            record['exit_requested'] = bool(strategy.net_qty)
            if filled:
                strategy.fees += strategy.config.fee_per_order
            strategy.done = strategy.net_qty == 0
            record['message'] = f'{intent["state"]} after {filled}/{abs(intent["delta"])} fills; closing actual residual exposure'
            if intent['desired'] == 0 and strategy.net_qty:
                # A rejected/partial exit must not produce an endless stream of
                # replacement orders. Reconcile and explicitly retry the exit.
                with self.lock:
                    self.records[record['id']]['exit_requested'] = False
                    self.records[record['id']]['resume_requested'] = False
                record['exit_requested'] = record['resume_requested'] = False
                record['status'] = 'paused'
                record['message'] = 'Exit did not fully fill. Exposure remains; check Dhan and click Exit & Stop to retry.'
        record['orders'].append(deepcopy(intent))
        record['pending'] = None
        record['strategy'] = asdict(strategy)
        if strategy.done:
            record['pnl'] = strategy.realized - strategy.fees
        record['status'] = 'done' if strategy.done else record['status']
        self._save(record, {'event': 'order_terminal', 'order_id': intent['order_id'], 'filled': filled})

    def step(self, record, broker, quote):
        strategy = Ladder(**record['strategy'])
        strategy = self._observed(record, strategy)
        now = self.now()
        if quote and quote.get('source') and not fresh(quote, now, strategy.config.max_quote_age_seconds):
            quote = None
        if record['account'] != broker.account:
            raise RuntimeError('Saved algo account does not match active account')
        if record['mode'] == 'live':
            broker.connect_orders()
        if record['pending']:
            self._reconcile_order(record, strategy, broker, quote)
            return
        if record['session_date'] != now.date().isoformat():
            if record['mode'] == 'live':
                self._position_check(record, strategy, broker)
            if strategy.net_qty:
                raise RuntimeError('Prior-day exposure requires manual broker reconciliation; no overnight orders are sent')
            record['status'] = 'done'
            self._save(record)
            return
        if record['status'] == 'paused' and not record['resume_requested'] and not record['exit_requested']:
            return
        if record['mode'] == 'live' and record['resume_requested']:
            self._preflight(record, strategy, broker)
        if record['resume_requested']:
            with self.lock:
                self.records[record['id']]['resume_requested'] = False
            record['resume_requested'] = False
        record['status'] = 'running'
        if not time(9, 15) <= now.time() < time(15, 30):
            raise RuntimeError('Market is closed; verify any open exposure with Dhan')
        cutoff = now.time() >= time.fromisoformat(strategy.config.square_off)
        if (record['exit_requested'] or cutoff) and not strategy.net_qty:
            strategy.done = True
            record['status'] = 'done'
            record['strategy'] = asdict(strategy)
            record['message'] = 'Stopped with no position'
            self._save(record)
            return
        if (record['exit_requested'] or cutoff) and strategy.net_qty:
            # Flattening a reconciled live position does not need a price signal.
            if record['mode'] == 'live':
                self._submit(record, strategy, {'desired': 0, 'reason': 'manual_exit' if record['exit_requested'] else 'square_off'}, broker, quote)
                return
        if quote and (now - datetime.fromisoformat(quote['time'])).total_seconds() > strategy.config.max_quote_age_seconds:
            quote = None
        depth_ok = bool(quote and (fresh(quote, now, strategy.config.max_quote_age_seconds, depth=True)
                                  if quote.get('source') else 'bid' in quote and 'ask' in quote))
        action = record.get('trigger')
        if record['exit_requested'] or cutoff:
            action = {'desired': 0, 'reason': 'manual_exit' if record['exit_requested'] else 'square_off'}
        if not quote and not action:
            record['message'] = 'Fresh bid/ask unavailable. No new order; app-managed exits cannot trigger without fresh data.'
            record['strategy'] = asdict(strategy)
            self._save(record)
            return
        record['quote'] = quote
        if not strategy.started and strategy.config.sizing == 'capital':
            if not depth_ok:
                record['message'] = 'Waiting for fresh bid/ask to size entry'
                self._save(record)
                return
            strategy.base_qty = int(strategy.config.capital / (quote['ask'] if strategy.initial_side > 0 else quote['bid']))
            if strategy.base_qty < 1:
                raise ValueError('Capital is too small for one share')
        price = quote.get('ltp') if quote else None
        if price is None and quote and not quote.get('source'):
            price = quote['bid'] if strategy.net_qty > 0 else quote['ask'] if strategy.net_qty < 0 else (quote['ask'] if strategy.initial_side > 0 else quote['bid'])
        if not action and price is not None:
            action = strategy.action(price, cutoff, quote.get('ask' if strategy.side > 0 else 'bid'))
        if action:
            record['trigger'] = action
        record['strategy'] = asdict(strategy)
        if price is not None:
            record['pnl'] = strategy.mark(price)
        record['message'] = ('Monitoring websocket LTP; cached bid/ask for execution' if quote and quote.get('source') == 'websocket'
                             else 'REST fallback: monitoring LTP; websocket unavailable or stale')
        self._save(record)
        if action:
            if not depth_ok and (record['mode'] == 'paper' or action['desired'] != 0):
                record['message'] = 'Signal retained; waiting for fresh bid/ask before execution'
                self._save(record)
                return
            if action['reason'] == 'add' and strategy.config.sizing == 'capital':
                size = int(strategy.config.capital / quote['ask' if strategy.side > 0 else 'bid'])
                action = {**action, 'desired': strategy.net_qty + strategy.side * size}
            self._submit(record, strategy, action, broker, quote)

    def _run(self):
        while not self.stop_event.is_set():
            self.wake.clear()
            with self.lock:
                active = [deepcopy(row) for row in self.records.values() if row['status'] != 'done'
                          and (row['status'] != 'paused' or row['pending'] or row['exit_requested'] or row['resume_requested'])]
                active.sort(key=lambda row: 0 if (row['exit_requested'] or row.get('trigger')
                    or (self.observations.get(row['id']) or {}).get('trigger')) else 1 if row['pending'] else 2)
            if active:
                try:
                    broker = self._get_broker()
                    broker.connect_market([row['security_id'] for row in active], self.on_tick,
                                          min(row['strategy']['settings']['max_quote_age_seconds'] for row in active))
                    quotes = broker.market_quotes()
                except Exception as exc:
                    # Existing orders still require REST reconciliation if market data fails.
                    quotes = {}
                    broker = self.broker
                    if broker is None or not broker.identity_ok():
                        for row in active:
                            row['status'], row['message'] = 'paused', str(exc)
                            self._save(row)
                        broker = None
                if broker:
                    for row in active:
                        if self.stop_event.is_set():
                            break
                        try:
                            self.step(row, broker, quotes.get(str(row['security_id'])))
                        except Exception as exc:
                            row['status'], row['message'] = 'paused', str(exc)
                            self._save(row, {'event': 'paused', 'reason': str(exc)})
            elif self.broker and getattr(self.broker, 'market_feed', None):
                self.broker.market_feed.subscribe([])
            self.wake.wait(.25)

    def shutdown(self):
        self.stop_event.set()
        self.wake.set()
        if self.broker:
            self.broker.close()
        if self.thread:
            self.thread.join(timeout=15)
        # Keep ownership if a broker call is still running; never allow two senders.
        if not self.thread or not self.thread.is_alive():
            self.journal.release()

    def backtest(self, request):
        previous = getattr(self.engine._request_context, 'volume_filters', None)
        self.engine._request_context.volume_filters = self.engine._volume_filters
        try:
            return self._backtest(request)
        finally:
            if previous is None:
                del self.engine._request_context.volume_filters
            else:
                self.engine._request_context.volume_filters = previous

    def _backtest(self, request):
        target, now = request.target_date, self.now()
        if target > now.date() or target < now.date() - timedelta(days=5 * 366):
            raise ValueError('Choose a past trading date within Dhan’s five-year intraday availability')
        if request.start_time >= request.settings.square_off:
            raise ValueError('Backtest entry time must be before square-off')
        resolved, missing = self.engine.resolver.resolve([request.symbol.upper()])
        if missing or request.symbol.upper() not in resolved:
            raise ValueError('Stock could not be resolved')
        instrument = resolved[request.symbol.upper()]
        client = self.engine._client()
        bars = self.engine._fetch_backtest_history(client, instrument, target)
        daily = None
        if request.setup == 'possible' or self.engine.volume_filters.redwala_open_previous_close:
            daily = self.engine._fetch_daily_filter(client, instrument, target)
        start = datetime.combine(target, time.fromisoformat(request.start_time), tzinfo=market.IST)
        # Qualification sees only candles completed before the selected entry.
        prior = [bar for bar in bars if bar.end <= start]
        qualification = self.engine._build_backtest_row(instrument, target, prior, daily)
        if not qualification['possible_candidate' if request.setup == 'possible' else 'redwala_gira']:
            raise ValueError('This stock does not qualify for the selected setup on that date under the saved scanner filters')
        session = sorted((bar for bar in bars if start <= bar.start and bar.start.date() == target and bar.end <= now), key=lambda bar: bar.start)
        cutoff = datetime.combine(target, time.fromisoformat(request.settings.square_off), tzinfo=market.IST)
        session = [bar for bar in session if bar.start <= cutoff]
        expected = start
        for bar in session:
            if bar.start != expected:
                raise ValueError(f'Missing intraday candle at {expected:%H:%M}; cannot reliably replay orders')
            expected = bar.end
        if not session or session[0].start != start:
            raise ValueError('Selected entry candle is unavailable')
        settings = request.settings.model_copy(update={'mode': 'paper'})
        result = replay(session, settings, settings.side_for_setup(request.setup))
        result.update(symbol=instrument.symbol, target_date=target.isoformat(), setup=request.setup,
                      start_time=request.start_time, complete_through=session[-1].end.isoformat(),
                      truncated=session[-1].start < cutoff, qualification=qualification,
                      volume_filters=self.engine.volume_filters.model_dump())
        return result
