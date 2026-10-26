from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from app.algo_strategy import AlgoSettings, AlgoStart, AlgoBacktest, Ladder, paper_execute, replay
from app.algo_service import AlgoService
from app.algo_journal import Journal
from app.algo_broker import DhanAlgoBroker, position_qty
from app.dhan_scanner import Candle, IST, Instrument, ScannerEngine, StockState
from app.storage import ConfigStore

NOW = datetime(2026, 10, 16, 10, 0, tzinfo=IST)


def ladder(side=1, **kwargs):
    settings = AlgoSettings(sizing='quantity', quantity=500, slippage_bps=0, **kwargs)
    s = Ladder(settings.model_dump(), side, 500)
    paper_execute(s, s.action(100), 100, 100, NOW)
    return s


@pytest.mark.parametrize('side', [1, -1])
def test_ladder_reversal_and_target_locks_day(side):
    s = ladder(side, ladder=True)
    action = s.action(100 - side)
    assert action == {'desired': -side * 500, 'reason': 'reverse'}
    before = s.net_qty
    paper_execute(s, action, 100-side, 100-side, NOW)
    assert s.fills[-1]['qty'] == -side * 1000
    assert s.net_qty == -before
    assert s.reversals == 1
    target = s.levels()['target']
    action = s.action(target)
    assert action['reason'] == 'target'
    paper_execute(s, action, target, target, NOW)
    assert s.done and s.day_locked and s.net_qty == 0
    assert s.action(100) is None


@pytest.mark.parametrize('side', [1, -1])
def test_pyramids_original_reference_and_reversal_resets(side):
    s = ladder(side, ladder=True, pyramiding=True, max_adds=2)
    for _ in range(2):
        price = s.next_add
        action = s.action(price)
        assert action['reason'] == 'add'
        paper_execute(s, action, price, price, NOW)
    assert s.net_qty == side * 1500
    assert s.original == 100
    assert s.levels()['target'] == 100 * (1 + side*.04)
    assert s.stop == 100 * (1-side*.01)
    assert s.action(s.next_add) is None
    action = s.action(s.stop)
    assert action['desired'] == -side * 500
    paper_execute(s, action, s.stop, s.stop, NOW)
    assert s.fills[-1]['qty'] == -side * 2000
    assert s.adds == 0


def test_capital_sizing_for_each_add():
    settings = AlgoSettings(capital=50000, pyramiding=True, slippage_bps=0)
    s = Ladder(settings.model_dump(), 1, 500)
    paper_execute(s, s.action(100), 100, 100, NOW)
    action = s.action(101, entry_price=101.5)
    assert action['desired'] == 500 + int(50000/101.5)


@pytest.mark.parametrize('side', [1, -1])
def test_trailing_ratchets_and_fixed_stop_does_not(side):
    fixed, trail = ladder(side), ladder(side, trailing=True)
    fixed.action(100+side*2)
    trail.action(100+side*2)
    assert fixed.stop == 100*(1-side*.01)
    stop = trail.stop
    trail.action(100+side*1.5)
    assert trail.stop == stop
    assert trail.action(stop)['reason'] == 'stop'


def test_max_loss_and_reversal_limit_and_cutoff():
    s = ladder(ladder=True, max_loss=100)
    assert s.action(99.5)['reason'] == 'max_loss'
    assert s.day_locked
    assert ladder(ladder=True, max_reversals=0).action(99)['reason'] == 'stop'
    assert ladder(ladder=True).action(101, cutoff=True)['desired'] == 0


def test_partial_entry_uses_completed_average_for_original_stop():
    s = Ladder(AlgoSettings(sizing='quantity').model_dump(), 1, 10)
    s.fill(5,100,NOW,'a'); s.fill(5,102,NOW,'b')
    s.completed({'desired':10, 'reason':'entry', 'average_fill':101})
    assert s.original == 101 and s.stop == pytest.approx(99.99)
    s.fill(5,102,NOW,'b')
    assert s.net_qty == 10
    with pytest.raises(ValueError, match='changed'): s.fill(6,102,NOW,'b')


@pytest.mark.parametrize('field,value', [('capital',0), ('capital',float('nan')), ('target_pct',0),
 ('stop_pct',100), ('max_adds',-1), ('square_off','15:30'), ('quantity',0)])
def test_settings_reject_invalid_risk(field, value):
    with pytest.raises(ValidationError): AlgoSettings(**{field:value})


def test_replay_adverse_first_and_gap_price():
    settings = AlgoSettings(capital=50000, slippage_bps=0)
    bar = Candle(NOW,100,105,98,104,1000)
    result = replay([Candle(NOW-timedelta(minutes=1),100,100,100,100,1), bar], settings, 1)
    assert result['actions'][-1]['reason'] == 'stop'
    assert result['pnl'] == -500
    bars = [Candle(NOW,100,100,100,100,1), Candle(NOW+timedelta(minutes=1),95,96,94,95,1)]
    result = replay(bars, settings, 1)
    assert result['strategy']['fills'][-1]['price'] == 95
    assert result['pnl'] == -2500


class Broker:
    account = 'TEST'
    def __init__(self):
        self.socket = SimpleNamespace(connected=True)
        self.net = 0; self.sent = []; self.cancelled = []; self.trade_rows = []
        self.order_row = {}; self.external = []; self.fail_submit = False
    def connect_orders(self): pass
    def positions(self): return [dict(securityId='1', exchangeSegment='NSE_EQ', productType='INTRADAY', netQty=self.net)]
    def orders(self): return self.external
    def submit(self, sid, intent):
        self.sent.append(deepcopy(intent))
        if self.fail_submit: raise TimeoutError('lost response')
        return {'orderId':'O1', 'orderStatus':'PENDING'}
    def order(self, intent): return self.order_row
    def trades(self, oid): return self.trade_rows
    def cancel(self, oid): self.cancelled.append(oid)
    def close(self): pass
    def identity_ok(self): return True
    def fill(self, intent, quantity, status='PART_TRADED', price=100):
        self.order_row = dict(securityId='1', exchangeSegment='NSE_EQ', productType='INTRADAY',
            transactionType='BUY' if intent['delta']>0 else 'SELL', quantity=abs(intent['delta']),
            orderId='O1', correlationId=intent['correlation'], filledQty=quantity, orderStatus=status)
        self.trade_rows = [] if not quantity else [{**self.order_row, 'exchangeTradeId':'T1',
            'tradedQuantity':quantity, 'tradedPrice':price}]
        self.net = quantity if intent['delta']>0 else -quantity


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = ScannerEngine(ConfigStore(tmp_path/'config.json'))
    engine.store.update_credentials('TEST','NOT_A_REAL_TOKEN')
    engine._states = {'AAA':StockState(Instrument('AAA','1','AAA'), signal_session=NOW.date(),
        confirmation_status='confirmed', possible_candidate=True, redwala_gira=True)}
    service = AlgoService(engine)
    monkeypatch.setattr(service,'now',lambda:NOW)
    monkeypatch.setattr(service,'_launch',lambda:None)
    broker = Broker()
    yield service,broker
    service.shutdown()


def start(env, mode='live', **settings):
    service, broker = env
    sid=service.start(AlgoStart(symbol='AAA',setup='possible',settings=AlgoSettings(mode=mode,capital=50000,slippage_bps=0,**settings)))
    return deepcopy(service.records[sid])


def quote(price=100): return {'bid':price,'ask':price,'time':NOW.isoformat()}


def tick(price=100, bid=None, ask=None):
    return {'ltp': price, 'bid': price if bid is None else bid, 'ask': price if ask is None else ask,
            'time': NOW.isoformat(), 'depth_time': NOW.isoformat(), 'received_at': NOW.isoformat(),
            'source': 'websocket'}


@pytest.mark.parametrize('side', [1, -1])
def test_websocket_transient_stop_latches_before_recovery(env, side):
    service, broker = env
    record = start(env, mode='paper', ladder=True, first_direction='long' if side == 1 else 'short')
    service.step(record, broker, tick())
    service.on_tick('1', tick(100-side))
    service.on_tick('1', tick(100))
    service.step(record, broker, tick(100))
    assert record['strategy']['net_qty'] == -side*500
    assert record['strategy']['reversals'] == 1
    service.step(record, broker, tick(100))
    assert record['strategy']['reversals'] == 1  # Old latch cannot act on the new ladder.
    assert not broker.sent


def test_ltp_triggers_not_spread_and_depth_prices_paper_fill(env):
    service, broker = env
    record = start(env, mode='paper')
    service.step(record, broker, tick())
    service.on_tick('1', tick(100, bid=98, ask=102))
    service.step(record, broker, tick(100, bid=98, ask=102))
    assert record['strategy']['net_qty'] == 500
    service.on_tick('1', tick(99, bid=98, ask=100))
    service.step(record, broker, tick(99, bid=98, ask=100))
    assert record['strategy']['net_qty'] == 0
    assert record['strategy']['fills'][-1]['price'] == 98


@pytest.mark.parametrize('side', [1, -1])
def test_tick_trailing_highwater_and_target_survive_busy_worker(env, side):
    service, broker = env
    record = start(env, mode='paper', trailing=True, first_direction='long' if side == 1 else 'short')
    service.step(record, broker, tick())
    service.on_tick('1', tick(100+side*2))
    service.on_tick('1', tick(100+side*.5))
    service.on_tick('1', tick(100+side*2))
    service.step(record, broker, tick(100+side*2))
    assert record['strategy']['last_reason'] == 'stop'
    assert record['status'] == 'done'


def test_tick_target_latched_and_no_network_on_receiver(env, monkeypatch):
    service, broker = env
    record = start(env, mode='paper')
    service.step(record, broker, tick())
    def forbidden(*args, **kwargs):
        pytest.fail('Tick callback must not perform I/O')
    monkeypatch.setattr(service.journal, 'save', forbidden)
    monkeypatch.setattr(broker, 'submit', forbidden)
    service.on_tick('1', tick(104))
    service.on_tick('1', tick(100))
    obs = service.observations[record['id']]
    assert obs['trigger']['reason'] == 'target'
    assert obs['strategy'].day_locked


def test_missing_depth_retains_reverse_signal_until_available(env):
    service, broker = env
    record = start(env, mode='paper', ladder=True)
    service.step(record, broker, tick())
    q = tick(99); del q['bid']; del q['ask']
    service.on_tick('1', q)
    service.step(record, broker, q)
    assert record['strategy']['net_qty'] == 500
    assert record['trigger']['reason'] == 'reverse'
    service.on_tick('1', tick(100))
    service.step(record, broker, tick(100))
    assert record['strategy']['net_qty'] == -500


def test_triggered_live_flatten_needs_no_depth(env):
    service, broker = env
    record = start(env)
    service.step(record, broker, tick())
    broker.fill(record['pending'], 500, 'TRADED')
    service.step(record, broker, tick())
    q = tick(99); del q['bid']; del q['ask']
    service.on_tick('1', q)
    service.step(record, broker, q)
    assert broker.sent[-1]['desired'] == 0
    assert broker.sent[-1]['delta'] == -500


def test_stale_tick_cannot_trigger_and_no_per_tick_broker_reads(env, monkeypatch):
    service, broker = env
    record = start(env)
    service.step(record, broker, tick())
    broker.fill(record['pending'], 500, 'TRADED')
    service.step(record, broker, tick())
    q = tick(99); q['time'] = (NOW-timedelta(seconds=30)).isoformat()
    service.on_tick('1', q)
    def forbidden():
        pytest.fail('Monitoring without a signal must not poll broker state')
    monkeypatch.setattr(broker, 'positions', forbidden)
    monkeypatch.setattr(broker, 'orders', forbidden)
    service.step(record, broker, tick(100))
    assert record['pending'] is None and len(broker.sent) == 1


def test_risk_during_partial_fill_cancels_then_flattens_even_if_fill_finishes(env):
    service, broker = env
    record = start(env)
    service.step(record, broker, tick())
    broker.fill(record['pending'], 200)
    service.step(record, broker, tick())
    service.on_tick('1', tick(98))
    service.on_tick('1', tick(100))
    service.step(record, broker, tick())
    assert broker.cancelled == ['O1'] and len(broker.sent) == 1
    broker.trade_rows.append({**broker.trade_rows[0], 'exchangeTradeId': 'T2', 'tradedQuantity': 300})
    broker.order_row.update(filledQty=500, orderStatus='TRADED'); broker.net = 500
    service.step(record, broker, tick())
    assert record['exit_requested']
    service.step(record, broker, tick())
    assert broker.sent[-1]['desired'] == 0 and broker.sent[-1]['delta'] == -500


def test_exit_supersedes_add_if_tick_arrives_during_preflight(env, monkeypatch):
    service, broker = env
    record = start(env, pyramiding=True)
    service.step(record, broker, tick())
    broker.fill(record['pending'], 500, 'TRADED')
    service.step(record, broker, tick())
    service.on_tick('1', tick(101))
    original = broker.positions
    def positions():
        service.on_tick('1', tick(98))
        return original()
    monkeypatch.setattr(broker, 'positions', positions)
    service.step(record, broker, tick(101))
    assert broker.sent[-1]['reason'] == 'stop'
    assert broker.sent[-1]['delta'] == -500


def test_market_feed_snapshot_separate_from_order_socket(env):
    service, broker = env
    service.broker = broker
    broker.market_feed = SimpleNamespace(connected=True)
    broker.socket.connected = False
    snapshot = service.snapshot()
    assert snapshot['market_socket_connected'] and not snapshot['order_socket_connected']


def test_event_worker_uses_ticks_with_scanner_stopped_and_no_quote_poll(env, monkeypatch):
    service, broker = env
    record = start(env, mode='paper')
    subscriptions = []
    rounds = []
    monkeypatch.setattr(service, '_get_broker', lambda: broker)
    broker.connect_market = lambda ids, callback, max_age: subscriptions.append(ids)
    def quotes():
        rounds.append(1)
        if len(rounds) == 2:
            service.on_tick('1', tick(99))
            service.on_tick('1', tick(100))
        assert len(rounds) <= 2, 'Worker failed to execute retained tick signal'
        return {'1': tick()}
    broker.market_quotes = quotes
    original_step = service.step
    def step(row, *args):
        original_step(row, *args)
        if row['status'] == 'done':
            service.stop_event.set()
    monkeypatch.setattr(service, 'step', step)
    service._run()
    assert len(rounds) == 2 and subscriptions == [['1'], ['1']]
    assert service.records[record['id']]['strategy']['net_qty'] == 0
    assert not broker.sent


def test_partial_reverse_monitors_new_side_without_interrupting_old_side_close(env):
    service, broker = env
    record = start(env, ladder=True)
    service.step(record, broker, tick())
    broker.fill(record['pending'], 500, 'TRADED')
    service.step(record, broker, tick())
    service.on_tick('1', tick(99))
    service.step(record, broker, tick(99))
    assert broker.sent[-1]['delta'] == -1000
    # Give the second order distinct IDs, just as a real broker does.
    record['pending']['order_id'] = 'O2'
    broker.fill(record['pending'], 300, price=99)
    broker.order_row['orderId'] = 'O2'; broker.trade_rows[0]['orderId'] = 'O2'
    broker.net = 200
    service.step(record, broker, tick(99))
    assert record['strategy']['net_qty'] == 200 and not broker.cancelled
    broker.trade_rows.append({**broker.trade_rows[0], 'exchangeTradeId': 'T2', 'tradedQuantity': 300})
    broker.order_row.update(filledQty=600); broker.net = -100
    service.step(record, broker, tick(99))
    assert record['strategy']['net_qty'] == -100
    service.on_tick('1', tick(101))
    service.on_tick('1', tick(99))
    service.step(record, broker, tick(99))
    assert broker.cancelled == ['O2'] and len(broker.sent) == 2


def test_market_observation_does_not_erase_worker_day_lock_or_sizing(env):
    service, broker = env
    record = start(env, mode='paper')
    service.step(record, broker, tick())
    service.on_tick('1', tick())
    strategy = Ladder(**record['strategy'])
    strategy.day_locked = True
    strategy.base_qty = 499
    merged = service._observed(record, strategy)
    assert merged.day_locked and merged.base_qty == 499


@pytest.mark.parametrize('entered', [False, True])
def test_square_off_reached_during_preflight_never_opens_exposure(env, monkeypatch, entered):
    service, broker = env
    record = start(env, ladder=True)
    if entered:
        service.step(record, broker, tick())
        broker.fill(record['pending'], 500, 'TRADED')
        service.step(record, broker, tick())
    original = broker.positions
    def positions():
        monkeypatch.setattr(service, 'now', lambda: NOW.replace(hour=15, minute=15))
        return original()
    monkeypatch.setattr(broker, 'positions', positions)
    service.step(record, broker, tick(99 if entered else 100))
    if entered:
        assert broker.sent[-1]['reason'] == 'square_off' and broker.sent[-1]['desired'] == 0
    else:
        assert not broker.sent and record['status'] == 'done'


def test_credentials_changed_during_preflight_blocks_submission(env, monkeypatch):
    service, broker = env
    record = start(env)
    monkeypatch.setattr(broker, 'identity_ok', lambda: False)
    with pytest.raises(RuntimeError, match='credentials changed'):
        service.step(record, broker, tick())
    assert not broker.sent and record['pending'] is None


def test_fallback_fetches_only_missing_data_off_the_order_worker(env, monkeypatch):
    from app.algo_feed import AlgoMarketFeed
    import app.algo_broker as adapter
    service, _ = env
    monkeypatch.setattr(service.engine, '_client', lambda: SimpleNamespace())
    broker = DhanAlgoBroker(service.engine, lambda: None)
    emitted = []
    broker.market_feed = AlgoMarketFeed('TEST', 'FAKE', lambda: None,
        lambda sid, q: emitted.append((sid, q)))
    broker.market_feed.subscribe(['1', '2'])
    broker.market_feed.accept('1', tick())
    class Frozen:
        @staticmethod
        def now(tz): return NOW
    monkeypatch.setattr(adapter, 'datetime', Frozen)
    class StopAfterWait:
        done = False
        def is_set(self): return self.done
        def wait(self, seconds):
            assert seconds == 1.05
            self.done = True
    broker._market_stop = StopAfterWait()
    calls = []
    def quotes(ids, now, age):
        calls.append(ids)
        return {'2': {**tick(), 'source': 'rest'}}
    monkeypatch.setattr(broker, 'quotes', quotes)
    broker._quote_fallback()
    assert calls == [['2']]
    assert broker.market_quotes()['1']['source'] == 'websocket'
    assert broker.market_quotes()['2']['source'] == 'rest'
    assert [sid for sid, _ in emitted] == ['1', '2']


def test_paper_entry_and_reversal_use_no_broker_orders(env):
    service,broker=env; record=start(env,mode='paper',ladder=True)
    service.step(record,broker,quote())
    assert record['strategy']['net_qty']==500
    service.step(record,broker,quote(99))
    assert record['strategy']['net_qty']==-500
    assert not broker.sent


def test_live_ack_is_not_fill_and_partial_trade_is_deduplicated(env):
    service,broker=env; record=start(env)
    service.step(record,broker,quote())
    assert record['strategy']['net_qty']==0 and record['pending']['order_id']=='O1'
    broker.fill(record['pending'],200)
    service.step(record,broker,quote())
    service.step(record,broker,quote())
    assert record['strategy']['net_qty']==200 and len(record['strategy']['fills'])==1
    assert len(broker.sent)==1
    broker.trade_rows.append({**broker.trade_rows[0], 'exchangeTradeId':'T2','tradedQuantity':300})
    broker.order_row.update(filledQty=500,orderStatus='TRADED'); broker.net=500
    service.step(record,broker,quote())
    assert record['pending'] is None and record['strategy']['net_qty']==500
    assert record['strategy']['original']==100


def test_uncertain_submission_is_reconciled_without_resend(env):
    service,broker=env; record=start(env); broker.fail_submit=True
    service.step(record,broker,quote())
    assert record['pending']['state']=='UNCERTAIN'
    broker.fill(record['pending'],500,'TRADED')
    service.step(record,broker,quote())
    assert len(broker.sent)==1 and record['strategy']['net_qty']==500


def test_intent_is_durable_before_submit(env,monkeypatch):
    service,broker=env; record=start(env)
    original=broker.submit
    def submit(sid,intent):
        saved=service.journal.load()[0]
        assert saved['pending']['correlation']==intent['correlation']
        assert saved['pending']['state']=='SUBMITTING'
        return original(sid,intent)
    monkeypatch.setattr(broker,'submit',submit)
    service.step(record,broker,quote())


def test_partial_cancel_flattens_only_actual_exposure(env):
    service,broker=env; record=start(env)
    service.step(record,broker,quote()); broker.fill(record['pending'],200,'CANCELLED')
    service.step(record,broker,quote())
    assert record['exit_requested'] and record['strategy']['net_qty']==200
    service.step(record,broker,quote())
    assert broker.sent[-1]['delta']==-200 and broker.sent[-1]['desired']==0


def test_pending_order_cancel_waits_for_final_state(env):
    service,broker=env; record=start(env)
    service.step(record,broker,quote()); broker.fill(record['pending'],200)
    record['exit_requested']=True
    service.step(record,broker,quote()); service.step(record,broker,quote())
    assert broker.cancelled==['O1'] and len(broker.sent)==1
    assert record['pending'] is not None


def test_rejected_exit_pauses_without_automatic_order_loop(env):
    service,broker=env; record=start(env)
    service.step(record,broker,quote()); broker.fill(record['pending'],500,'TRADED')
    service.step(record,broker,quote()); record['exit_requested']=True
    service.step(record,broker,quote())
    broker.fill(record['pending'],0,'REJECTED'); broker.net=500
    service.step(record,broker,quote())
    assert record['status']=='paused' and not record['exit_requested']
    service.step(record,broker,quote())
    assert len(broker.sent)==2


@pytest.mark.parametrize('problem',['quantity','external','socket','stale'])
def test_preflight_blocks_unsafe_submission(env,problem):
    service,broker=env; record=start(env); q=quote()
    if problem=='quantity': broker.net=10
    if problem=='external': broker.external=[dict(securityId='1',exchangeSegment='NSE_EQ',productType='INTRADAY',orderId='OTHER',orderStatus='PENDING')]
    if problem=='socket': broker.socket.connected=False
    if problem=='stale': q['time']=(NOW-timedelta(seconds=30)).isoformat()
    try: service.step(record,broker,q)
    except RuntimeError: pass
    assert not broker.sent


def test_manual_live_exit_does_not_require_quote_or_socket(env):
    service,broker=env; record=start(env)
    service.step(record,broker,quote()); broker.fill(record['pending'],500,'TRADED')
    service.step(record,broker,quote()); record['exit_requested']=True; broker.socket.connected=False
    service.step(record,broker,None)
    assert broker.sent[-1]['delta']==-500


def test_reconciliation_disagreement_blocks_next_action(env):
    service,broker=env; record=start(env)
    service.step(record,broker,quote()); broker.fill(record['pending'],200)
    broker.order_row['filledQty']=500
    service.step(record,broker,quote())
    assert record['pending'] is not None and len(broker.sent)==1
    assert 'disagree' in record['message']


def test_restart_pauses_and_journal_has_exclusive_owner(env):
    service,broker=env; record=start(env,mode='paper')
    service.step(record,broker,quote())
    other=Journal(service.journal.path)
    with pytest.raises(RuntimeError,match='Another process'): other.acquire()
    service.shutdown()
    restarted=AlgoService(service.engine)
    assert restarted.records[record['id']]['status']=='paused'
    assert restarted.records[record['id']]['strategy']['net_qty']==500
    restarted.shutdown()


def test_duplicate_start_and_day_lock(env):
    service,broker=env; record=start(env,mode='paper')
    with pytest.raises(ValueError,match='already'): start(env,mode='paper')
    service.step(record,broker,quote()); service.step(record,broker,quote(104))
    assert record['status']=='done'
    with pytest.raises(ValueError,match='locked'): start(env,mode='paper')


def test_only_confirmed_current_day_setups_can_start(env):
    service,_=env
    service.engine._states['AAA'].confirmation_status='awaiting_confirmation'
    with pytest.raises(ValueError,match='confirmed'): start(env)
    service.engine._states['AAA'].confirmation_status='confirmed'
    service.engine._states['AAA'].signal_session=NOW.date()-timedelta(days=1)
    with pytest.raises(ValueError,match='confirmed'): start(env)
    with pytest.raises(ValidationError): AlgoStart(symbol='AAA',setup='retest')


def test_snapshot_settings_do_not_mutate_active_session(env):
    service,_=env; record=start(env,mode='paper')
    service.save_settings(AlgoSettings(target_pct=8))
    assert service.records[record['id']]['strategy']['settings']['target_pct']==4
    data=service.snapshot(); data['sessions'][0]['strategy']['net_qty']=999
    assert service.records[record['id']]['strategy']['net_qty']==0


@pytest.mark.parametrize('direction,side', [('setup',1),('long',1),('short',-1)])
def test_backtest_qualifies_without_future_bars_and_forces_paper(env,monkeypatch,direction,side):
    service,_=env; engine=service.engine
    day=NOW.date()-timedelta(days=1)
    first=datetime.combine(day,datetime.min.time(),tzinfo=IST).replace(hour=9,minute=15)
    bars=[Candle(first+timedelta(minutes=i),100,100,100,100,10) for i in range(3)]
    instrument=engine._states['AAA'].instrument
    monkeypatch.setattr(engine.resolver,'resolve',lambda symbols:({'AAA':instrument},[]))
    monkeypatch.setattr(engine,'_client',lambda:None)
    monkeypatch.setattr(engine,'_fetch_backtest_history',lambda *args:bars)
    monkeypatch.setattr(engine,'_fetch_daily_filter',lambda *args:{})
    def qualify(instrument,date,prior,daily):
        assert len(prior)==1 and prior[0].end.hour==9 and prior[0].end.minute==16
        return {'possible_candidate':True,'redwala_gira':False}
    monkeypatch.setattr(engine,'_build_backtest_row',qualify)
    result=service.backtest(AlgoBacktest(symbol='AAA',setup='possible',target_date=day,settings=AlgoSettings(mode='live',first_direction=direction)))
    assert result['strategy']['settings']['mode']=='paper'
    assert result['strategy']['initial_side']==side
    assert result['strategy']['fills'][0]['qty'] * side > 0
    assert result['truncated'] and result['strategy']['net_qty']==0
    bars.pop(1)
    with pytest.raises(ValueError,match='Missing'): service.backtest(AlgoBacktest(symbol='AAA',setup='possible',target_date=day))


def test_position_match_ignores_other_products():
    rows=[dict(securityId='1',exchangeSegment='NSE_EQ',productType=p,netQty=q) for p,q in [('CNC',300),('INTRADAY',-20)]]
    assert position_qty(rows,'1')==-20


@pytest.mark.parametrize('setup,enabled,limit,passes', [
    ('redwala', False, 0, True), ('redwala', True, 1, True),
    ('redwala', True, .99, False), ('possible', True, 4, True),
    ('possible', True, 3.99, False),
])
def test_algo_backtest_obeys_setup_price_filters(env, monkeypatch, setup, enabled, limit, passes):
    from app.schemas import VolumeFilterSettings
    from app.daily_filter import calculate_daily_filter
    from test_daily_filter import daily_data
    service, _ = env
    engine = service.engine
    day = NOW.date() - timedelta(days=1)
    first = datetime.combine(day, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15)
    close = 99 if setup == 'redwala' else 102
    bars = [Candle(first - timedelta(days=n), 100, 101, 100, 101, 100_000) for n in (1, 2, 3)]
    bars += [Candle(first, 101, max(101, close), min(101, close), close, 500_000),
             Candle(first + timedelta(minutes=1), close, close, close, close, 100)]
    daily = {**calculate_daily_filter(daily_data(), day), 'previous_close': 100,
             'previous_high': 104, 'previous_low': 100}
    engine._volume_filters = VolumeFilterSettings(
        redwala_open_previous_close=enabled if setup == 'redwala' else False,
        redwala_open_gap_max=limit, pdhl_filter=True, pdhl_max=limit if setup == 'possible' else 0)
    instrument = engine._states['AAA'].instrument
    monkeypatch.setattr(engine.resolver, 'resolve', lambda *_: ({'AAA': instrument}, []))
    monkeypatch.setattr(engine, '_client', lambda: None)
    monkeypatch.setattr(engine, '_fetch_backtest_history', lambda *_: bars)
    calls = []
    def fetch(*_):
        calls.append(1)
        return daily
    monkeypatch.setattr(engine, '_fetch_daily_filter', fetch)
    request = AlgoBacktest(symbol='AAA', setup=setup, target_date=day)
    if passes:
        result = service.backtest(request)
        assert result['strategy']['fills']
    else:
        with pytest.raises(ValueError, match='does not qualify'):
            service.backtest(request)
    assert bool(calls) is (setup == 'possible' or enabled)


@pytest.mark.parametrize('mode',['paper','live'])
def test_exit_click_during_submission_prevents_new_entry(env,monkeypatch,mode):
    service,broker=env; record=start(env,mode=mode)
    original=service._save
    def save(row,event=None):
        original(row,event)
        if event and event.get('event')=='intent_before_submission':
            service.command(row['id'],'exit')
    monkeypatch.setattr(service,'_save',save)
    if mode=='paper':
        service.command(record['id'],'exit')
        record=deepcopy(service.records[record['id']])
    service.step(record,broker,quote())
    assert not broker.sent and record['strategy']['net_qty']==0


def test_trade_identity_mismatch_blocks_application(env):
    service,broker=env; record=start(env)
    service.step(record,broker,quote()); broker.fill(record['pending'],200)
    broker.trade_rows[0]['securityId']='999'
    with pytest.raises(RuntimeError,match='different'): service.step(record,broker,quote())
    assert record['strategy']['net_qty']==0


def test_cancel_retry_is_bounded_and_never_resubmits(env,monkeypatch):
    service,broker=env; record=start(env)
    service.step(record,broker,quote()); broker.fill(record['pending'],100)
    record['exit_requested']=True
    for n in range(6):
        monkeypatch.setattr(service,'now',lambda n=n:NOW+timedelta(seconds=n*6))
        service.step(record,broker,None)
    assert len(broker.cancelled)==3 and len(broker.sent)==1


def test_broker_quotes_use_shared_throttle_and_reject_stale_depth(env,monkeypatch):
    service,_=env; engine=service.engine
    client=SimpleNamespace(quote_data=lambda *a:None)
    monkeypatch.setattr(engine,'_client',lambda:client)
    calls=[]
    good={'depth':{'buy':[{'price':99,'quantity':10}], 'sell':[{'price':101,'quantity':20}]},
          'last_trade_time':NOW.strftime('%d/%m/%Y %H:%M:%S')}
    rows={'1':good,'2':{**good,'last_trade_time':(NOW-timedelta(minutes=1)).strftime('%d/%m/%Y %H:%M:%S')},
          '3':{**good,'depth':{'buy':[{'price':102,'quantity':1}],'sell':[{'price':101,'quantity':1}]}}}
    def shared(method,securities):
        calls.append(securities)
        return {'status':'success','data':{'NSE_EQ':rows}}
    monkeypatch.setattr(engine,'_quote_call',shared)
    broker=DhanAlgoBroker(engine,lambda:None)
    result=broker.quotes(['1','2','3'],NOW)
    assert list(result)==['1'] and result['1']['bid']==99 and len(calls)==1


def test_broker_submission_uses_market_intraday_and_correlation(env,monkeypatch):
    service,_=env; calls=[]
    client=SimpleNamespace(place_order=lambda **kwargs:(calls.append(kwargs) or {'status':'success','data':{'orderId':'o'}}))
    monkeypatch.setattr(service.engine,'_client',lambda:client)
    broker=DhanAlgoBroker(service.engine,lambda:None)
    broker.submit('1',{'delta':-1000,'correlation':'alg-test'})
    assert calls[0]['transaction_type']=='SELL' and calls[0]['quantity']==1000
    assert calls[0]['order_type']=='MARKET' and calls[0]['product_type']=='INTRADAY'
    assert calls[0]['tag']=='alg-test' and calls[0]['should_slice'] is False


def test_algo_api_contract_and_no_network(env,monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main
    service,broker=env
    monkeypatch.setattr(main,'scanner',service.engine)
    service.engine._algo=service
    client=TestClient(main.app)
    assert client.post('/api/algo/start',json={'symbol':'AAA','setup':'afternoon'}).status_code==422
    result=client.post('/api/algo/start',json={'symbol':'AAA','setup':'possible','settings':{'capital':50000}})
    assert result.status_code==200
    sid=result.json()['session_id']; record=deepcopy(service.records[sid])
    service.step(record,broker,quote())
    response=client.get('/api/state')
    assert response.status_code==200 and response.json()['algo']['sessions'][0]['strategy']['net_qty']==500
    assert client.post('/api/algo/'+sid+'/exit',json={}).status_code==200
    service.step(deepcopy(service.records[sid]),broker,quote())
    assert service.records[sid]['status']=='done'
    assert not broker.sent



def test_order_socket_authenticates_and_only_wakes_reconciliation(monkeypatch):
    import asyncio, json
    from app.algo_broker import OrderSocket
    events=[]
    socket=OrderSocket('TEST','FAKE_TOKEN',lambda:events.append('wake'))
    sent=[]
    class WS:
        async def send(self,message): sent.append(json.loads(message))
        async def recv(self):
            socket.stop.set()
            return json.dumps({'Type':'order_alert','Data':{'OrderNo':'O1','TradedQty':500}})
    class Connection:
        async def __aenter__(self): return WS()
        async def __aexit__(self,*args): pass
    monkeypatch.setattr('websockets.connect',lambda *a,**kw:Connection())
    asyncio.run(socket.run())
    assert sent==[{'LoginReq':{'MsgCode':42,'ClientId':'TEST','Token':'FAKE_TOKEN'},'UserType':'SELF'}]
    assert events==['wake','wake'] and not socket.connected


def test_replay_maximum_loss_executes_at_threshold():
    settings=AlgoSettings(capital=50000,slippage_bps=0,max_loss=100)
    result=replay([Candle(NOW-timedelta(minutes=1),100,100,100,100,1),
                   Candle(NOW,100,100,99.5,99.8,100)],settings,1)
    assert result['actions'][-1]['reason']=='max_loss'
    assert result['pnl']==pytest.approx(-100)


@pytest.mark.parametrize('setup,direction,side', [
    ('possible','setup',1),('redwala','setup',-1),
    ('possible','short',-1),('redwala','long',1),
    ('possible','long',1),('redwala','short',-1),
])
@pytest.mark.parametrize('mode',['paper','live'])
def test_selected_first_direction_controls_entry_and_reversal(env,setup,direction,side,mode):
    service,broker=env
    settings=AlgoSettings(mode=mode,capital=50000,first_direction=direction,ladder=True,slippage_bps=0)
    sid=service.start(AlgoStart(symbol='AAA',setup=setup,settings=settings))
    record=deepcopy(service.records[sid])
    assert record['strategy']['initial_side']==side
    service.step(record,broker,{'bid':99,'ask':100,'time':NOW.isoformat()})
    quantity=int(50000/(100 if side>0 else 99))
    if mode=='live':
        assert broker.sent[0]['delta']==side*quantity
        assert broker.sent[0]['reason']=='entry'
    else:
        assert record['strategy']['net_qty']==side*quantity
        price=record['strategy']['stop']
        service.step(record,broker,quote(price))
        assert record['strategy']['net_qty']==-side*quantity
        assert record['strategy']['reversals']==1
    service.save_settings(AlgoSettings(first_direction='short' if side>0 else 'long'))
    assert service.records[sid]['strategy']['initial_side']==side


def test_first_direction_backwards_compatible_and_validated():
    assert AlgoSettings.model_validate({}).side_for_setup('possible')==1
    assert AlgoSettings.model_validate({}).side_for_setup('redwala')==-1
    with pytest.raises(ValidationError): AlgoSettings(first_direction='random')


@pytest.mark.parametrize('side', [1,-1])
def test_opening_extreme_is_not_revisited_after_close_reversal(side):
    # Dhan POONAWALLA 2026-10-12, 09:18 through 09:23. Reflect prices
    # for the symmetric short-to-long opening-low regression.
    prices=[(478.9,482.7,478.65,480.9),(481.95,484,480.6,480.6),
            (480.1,482.95,480.1,481),(481.7,481.7,478.15,479.1),
            (479.05,479.05,473.05,473.75),(473.95,476.5,473.5,474.55)]
    if side<0:
        prices=[(1000-o,1000-l,1000-h,1000-c) for o,h,l,c in prices]
    start=NOW.replace(hour=9,minute=18)
    bars=[Candle(start+timedelta(minutes=i),o,h,l,c,1000) for i,(o,h,l,c) in enumerate(prices)]
    settings=AlgoSettings(sizing='quantity',quantity=6,ladder=True,pyramiding=True,
        stop_pct=1,target_pct=4,slippage_bps=5,fee_per_order=7,max_loss=150)
    result=replay(bars,settings,side)
    reversals=[a for a in result['actions'] if a['reason']=='reverse']
    assert len(reversals)==1
    assert reversals[0]['time']==bars[4].end.isoformat()
    assert reversals[0]['candle_start']==bars[4].start.isoformat()
    assert reversals[0]['desired']==-side*6
    assert not any(a['reason']=='max_loss' for a in result['actions'])
    reverse_fill=next(f for f in result['strategy']['fills'] if f.get('candle_start')==bars[4].start.isoformat())
    assert reverse_fill['qty']==(-18 if side>0 else 12)


@pytest.mark.parametrize('side', [1,-1])
def test_backtest_ignores_stop_touch_that_recovers_before_close(side):
    prices=[(100,100,100,100),(100,100,98,99.5),(99.5,99.5,99.5,99.5)]
    if side<0:
        prices=[(200-o,200-l,200-h,200-c) for o,h,l,c in prices]
    bars=[Candle(NOW+timedelta(minutes=i),o,h,l,c,1) for i,(o,h,l,c) in enumerate(prices)]
    result=replay(bars,AlgoSettings(sizing='quantity',quantity=1,ladder=True,trailing=True,slippage_bps=0),side)
    assert not any(a['reason']=='reverse' for a in result['actions'])
    assert result['actions'][-1]['reason']=='end_of_data'


def test_max_loss_trigger_tolerates_float_roundoff_at_exact_threshold():
    s=Ladder(AlgoSettings(capital=3000,pyramiding=True,ladder=True,max_loss=150,fee_per_order=7).model_dump(),1,6)
    for desired,reason,price in [(6,'entry',478.9),(12,'add',483.9308444999999),
                                (-6,'reverse',474.34805549999993),(6,'reverse',478.85199028697246)]:
        paper_execute(s,{'desired':desired,'reason':reason},price,price,NOW)
    level=s.average+(-s.config.max_loss-s.realized+s.fees)/s.net_qty
    assert s.mark(level)==pytest.approx(-150)
    assert s.action(level)=={'desired':0,'reason':'max_loss'}
    assert s.day_locked



def test_arcil_long_close_entry_does_not_use_earlier_low():
    start=NOW.replace(hour=9,minute=17)
    prices=[(149.42,151.29,149.18,150.96),(151,151.9,150.65,151.8),
            (151.45,151.72,149.6,150.27),(150.22,151.9,149.82,151.19)]
    bars=[Candle(start+timedelta(minutes=i),o,h,l,c,100) for i,(o,h,l,c) in enumerate(prices)]
    result=replay(bars,AlgoSettings(capital=3000,ladder=True,pyramiding=True,
        max_loss=200,slippage_bps=5,fee_per_order=7),-1)
    reversals=[a for a in result['actions'] if a['reason']=='reverse']
    assert len(reversals)==1
    assert reversals[0]['time']==bars[0].end.isoformat()
    assert reversals[0]['execution']=='candle_close'
    assert result['strategy']['fills'][1]['price']==pytest.approx(150.96*1.0005)
    assert result['strategy']['fills'][1]['qty']==40
    assert result['strategy']['stop']==pytest.approx(150.96*1.0005*.99)
    assert result['reversal_timing']=='candle_close'
    assert result['pnl']==pytest.approx(result['strategy']['realized']-3*7)


@pytest.mark.parametrize('side',[1,-1])
def test_trailing_reversal_is_confirmed_once_at_close(side):
    prices=[(100,100,100,100),(100,103,100,101),(101,101,101,101)]
    if side<0:
        prices=[(200-o,200-l,200-h,200-c) for o,h,l,c in prices]
    bars=[Candle(NOW+timedelta(minutes=i),o,h,l,c,1) for i,(o,h,l,c) in enumerate(prices)]
    result=replay(bars,AlgoSettings(sizing='quantity',quantity=1,ladder=True,trailing=True,slippage_bps=0),side)
    reversals=[a for a in result['actions'] if a['reason']=='reverse']
    assert len(reversals)==1
    assert reversals[0]['time']==bars[1].end.isoformat()
    assert result['strategy']['fills'][1]['price']==bars[1].close


def test_backtest_does_not_reverse_at_end_of_data_or_square_off():
    bars=[Candle(NOW,100,100,98,98,1)]
    settings=AlgoSettings(sizing='quantity',quantity=1,ladder=True,slippage_bps=0)
    assert replay(bars,settings,1)['actions'][-1]['reason']=='end_of_data'
    bars.append(Candle(NOW+timedelta(minutes=1),98,98,98,98,1))
    settings=settings.model_copy(update={'square_off':'10:01'})
    result=replay(bars,settings,1)
    assert [a['reason'] for a in result['actions']]==['entry','square_off']


def test_live_reversal_still_submits_immediately_when_stop_is_hit(env):
    service,broker=env; record=start(env,ladder=True)
    service.step(record,broker,quote()); broker.fill(record['pending'],500,'TRADED')
    service.step(record,broker,quote())
    service.step(record,broker,quote(99))
    assert len(broker.sent)==2
    assert broker.sent[-1]['reason']=='reverse' and broker.sent[-1]['delta']==-1000
    assert broker.sent[-1]['created_at']==NOW.isoformat()


@pytest.mark.parametrize('side',[1,-1])
@pytest.mark.parametrize('close',[101,99.5])
def test_entry_candle_ignores_extremes_regardless_of_colour(side,close):
    prices=[(100,110,90,close),(close,close,close,close)]
    if side<0:
        prices=[(200-o,200-l,200-h,200-c) for o,h,l,c in prices]
    bars=[Candle(NOW+timedelta(minutes=i),o,h,l,c,1) for i,(o,h,l,c) in enumerate(prices)]
    result=replay(bars,AlgoSettings(sizing='quantity',quantity=1,slippage_bps=0),side)
    assert [a['reason'] for a in result['actions']]==['entry','end_of_data']
    assert result['entry_candle_checks']=='close_only'


@pytest.mark.parametrize('side',[1,-1])
@pytest.mark.parametrize('close,reason',[(105,'target'),(98,'stop')])
def test_entry_close_can_exit_at_close_not_intraminute_threshold(side,close,reason):
    prices=(100,110,90,close)
    if side<0:
        o,h,l,c=prices; prices=(200-o,200-l,200-h,200-c)
    result=replay([Candle(NOW,*prices,1)],AlgoSettings(sizing='quantity',quantity=1,slippage_bps=0,fee_per_order=7),side)
    assert result['actions'][-1]['reason']==reason
    assert result['strategy']['fills'][-1]['price']==prices[-1]
    assert result['strategy']['fills'][-1]['time']==(NOW+timedelta(minutes=1)).isoformat()
    assert result['strategy']['fills'][-1]['execution']=='candle_close'
    assert result['pnl']==pytest.approx((prices[-1]-100)*side-14)


@pytest.mark.parametrize('side',[1,-1])
def test_following_candle_resumes_ohlc_stop_checks(side):
    prices=[(100,110,90,101),(101,103,98,102)]
    if side<0:
        prices=[(200-o,200-l,200-h,200-c) for o,h,l,c in prices]
    bars=[Candle(NOW+timedelta(minutes=i),o,h,l,c,1) for i,(o,h,l,c) in enumerate(prices)]
    result=replay(bars,AlgoSettings(sizing='quantity',quantity=1,slippage_bps=0),side)
    assert result['actions'][-1]['reason']=='stop'
    assert result['strategy']['fills'][-1]['price']==100-side
    assert result['pnl']==pytest.approx(-1)


@pytest.mark.parametrize('side',[1,-1])
def test_entry_high_low_do_not_move_trailing_watermark(side):
    prices=[(100,120,80,102),(102,102,101.5,102)]
    if side<0:
        prices=[(200-o,200-l,200-h,200-c) for o,h,l,c in prices]
    bars=[Candle(NOW+timedelta(minutes=i),o,h,l,c,1) for i,(o,h,l,c) in enumerate(prices)]
    result=replay(bars,AlgoSettings(sizing='quantity',quantity=1,target_pct=50,stop_pct=10,trailing=True,slippage_bps=0),side)
    assert [a['reason'] for a in result['actions']]==['entry','end_of_data']
    assert result['strategy']['best']==100+side*2


@pytest.mark.parametrize('close,adds',[(100.5,0),(103,1)])
def test_entry_candle_pyramid_uses_close_once(close,adds):
    bars=[Candle(NOW,100,110,90,close,1),Candle(NOW+timedelta(minutes=1),close,close,close,close,1)]
    result=replay(bars,AlgoSettings(sizing='quantity',quantity=1,pyramiding=True,slippage_bps=0),1)
    actions=[a for a in result['actions'] if a['reason']=='add']
    assert len(actions)==adds
    if adds:
        assert actions[0]['time']==bars[0].end.isoformat()
        assert result['strategy']['fills'][1]['price']==close
