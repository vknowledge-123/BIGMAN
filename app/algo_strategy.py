"""Fill-driven ladder strategy shared by paper execution and historical replay."""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlgoSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    mode: Literal['paper', 'live'] = 'paper'
    first_direction: Literal['setup', 'long', 'short'] = 'setup'
    sizing: Literal['quantity', 'capital'] = 'capital'
    quantity: int = Field(default=1, ge=1, le=100000)
    capital: float = Field(default=10000, gt=0, allow_inf_nan=False)
    target_pct: float = Field(default=4, gt=0, le=100, allow_inf_nan=False)
    stop_pct: float = Field(default=1, gt=0, lt=100, allow_inf_nan=False)
    trailing: bool = False
    trailing_pct: float = Field(default=1, gt=0, lt=100, allow_inf_nan=False)
    ladder: bool = False
    pyramiding: bool = False
    max_adds: int = Field(default=2, ge=0, le=20)
    reference: Literal['average', 'original'] = 'original'
    reversal_size: Literal['initial', 'accumulated'] = 'initial'
    max_reversals: int = Field(default=20, ge=0, le=100)
    max_loss: float = Field(default=10000, gt=0, allow_inf_nan=False)
    square_off: str = '15:15'
    slippage_bps: float = Field(default=5, ge=0, le=100, allow_inf_nan=False)
    fee_per_order: float = Field(default=0, ge=0, allow_inf_nan=False)
    order_timeout_seconds: int = Field(default=15, ge=5, le=60)
    max_quote_age_seconds: int = Field(default=5, ge=1, le=30)

    def side_for_setup(self, setup):
        if self.first_direction == 'long':
            return 1
        if self.first_direction == 'short':
            return -1
        return 1 if setup == 'possible' else -1

    @field_validator('square_off')
    @classmethod
    def check_time(cls, value):
        parsed = time.fromisoformat(value)
        if not time(9, 17) <= parsed <= time(15, 20) or parsed.second or len(value) != 5:
            raise ValueError('Square-off must be HH:MM between 09:17 and 15:20 IST')
        return value


class AlgoStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: str
    setup: Literal['possible', 'redwala']
    settings: AlgoSettings = Field(default_factory=AlgoSettings)


class AlgoBacktest(AlgoStart):
    target_date: date
    start_time: str = '09:16'

    @field_validator('start_time')
    @classmethod
    def check_start(cls, value):
        parsed = time.fromisoformat(value)
        if not time(9, 16) <= parsed < time(15, 20) or len(value) != 5:
            raise ValueError('Start time must be HH:MM from 09:16 to before 15:20 IST')
        return value


@dataclass
class Ladder:
    settings: dict
    initial_side: int
    base_qty: int
    net_qty: int = 0
    average: float = 0
    original: float = 0
    best: float = 0
    stop: float = 0
    next_add: float = 0
    adds: int = 0
    reversals: int = 0
    realized: float = 0
    fees: float = 0
    started: bool = False
    done: bool = False
    day_locked: bool = False
    last_reason: str = ''
    fills: list = field(default_factory=list)

    @property
    def config(self):
        return AlgoSettings.model_validate(self.settings)

    @property
    def side(self):
        return 1 if self.net_qty > 0 else -1 if self.net_qty < 0 else 0

    def mark(self, price):
        return self.realized - self.fees + (price - self.average) * self.net_qty

    def levels(self):
        if not self.net_qty:
            return {}
        c = self.config
        reference = self.average if c.reference == 'average' else self.original
        return {'target': reference * (1 + self.side * c.target_pct / 100),
                'stop': self.stop, 'add': self.next_add if c.pyramiding and self.adds < c.max_adds else None}

    def update_risk(self, price):
        if not self.net_qty:
            return
        c, side = self.config, self.side
        reference = self.average if c.reference == 'average' else self.original
        self.best = max(self.best, price) if side > 0 else min(self.best or price, price)
        base = reference * (1 - side * c.stop_pct / 100)
        trail = self.best * (1 - side * c.trailing_pct / 100) if c.trailing else base
        candidates = [base, trail] + ([self.stop] if self.stop else [])
        self.stop = max(candidates) if side > 0 else min(candidates)

    def fill(self, signed_qty, price, stamp, fill_id):
        if not isinstance(signed_qty, int) or not signed_qty or not math.isfinite(price) or price <= 0:
            raise ValueError('Invalid execution fill')
        if any(row['id'] == fill_id for row in self.fills):
            prior = next(row for row in self.fills if row['id'] == fill_id)
            if prior['qty'] != signed_qty or prior['price'] != price:
                raise ValueError('Broker changed an already applied fill')
            return
        old_qty, old_side = self.net_qty, self.side
        new_qty = old_qty + signed_qty
        new_side = 1 if new_qty > 0 else -1 if new_qty < 0 else 0
        if old_qty and old_qty * signed_qty < 0:
            self.realized += (price - self.average) * min(abs(old_qty), abs(signed_qty)) * old_side
        if not old_qty or old_qty * signed_qty > 0:
            self.average = (self.average * abs(old_qty) + price * abs(signed_qty)) / abs(new_qty)
        elif new_side != old_side:
            self.average = price if new_qty else 0
        self.net_qty = new_qty
        if new_side and new_side != old_side:
            self.original = self.best = price
            self.stop = 0
            self.adds = 0
            self.next_add = price * (1 + new_side * self.config.stop_pct / 100)
        self.started = True
        self.fills.append({'id': fill_id, 'qty': signed_qty, 'price': price, 'time': str(stamp),
                           'net_qty': new_qty, 'realized': self.realized})
        self.update_risk(price)

    def action(self, price, cutoff=False, entry_price=None, *, allow_reversal=True):
        if self.done:
            return None
        if not self.started:
            return {'desired': self.initial_side * self.base_qty, 'reason': 'entry'}
        if not self.net_qty:
            self.done = True
            return None
        self.update_risk(price)
        c, side = self.config, self.side
        if cutoff:
            return {'desired': 0, 'reason': 'square_off'}
        if self.mark(price) <= -c.max_loss + 1e-9:
            self.day_locked = True
            return {'desired': 0, 'reason': 'max_loss'}
        levels = self.levels()
        if side * (price - levels['target']) >= -1e-9:
            self.day_locked = True
            return {'desired': 0, 'reason': 'target'}
        if side * (price - self.stop) <= 1e-9:
            if c.ladder and self.reversals < c.max_reversals:
                if not allow_reversal:
                    return None
                size = self.base_qty if c.reversal_size == 'initial' else abs(self.net_qty)
                return {'desired': -side * size, 'reason': 'reverse'}
            return {'desired': 0, 'reason': 'stop'}
        if levels['add'] and side * (price - levels['add']) >= -1e-9:
            size = self.base_qty if c.sizing == 'quantity' else int(c.capital / (entry_price or price))
            if size > 0:
                return {'desired': self.net_qty + side * size, 'reason': 'add'}
        return None

    def completed(self, intent):
        if self.net_qty != intent['desired']:
            raise ValueError('Order completion does not match intended position')
        self.last_reason = intent['reason']
        self.fees += self.config.fee_per_order
        if intent['reason'] in {'entry', 'reverse'} and self.net_qty:
            self.original = self.average
            # Partial executions can change the entry average; fixed stops use
            # the completed entry, while trailing retains the observed watermark.
            self.stop = 0
            self.next_add = self.average * (1 + self.side * self.config.stop_pct / 100)
            self.update_risk(self.average)
        if intent['reason'] == 'add':
            self.adds += 1
            # One increment per confirmed add, measured from its actual average fill.
            self.next_add = intent['average_fill'] * (1 + self.side * self.config.stop_pct / 100)
        if intent['reason'] == 'reverse':
            self.reversals += 1
        if self.net_qty == 0:
            self.done = True


def paper_execute(strategy, action, bid, ask, stamp):
    delta = action['desired'] - strategy.net_qty
    price = (ask if delta > 0 else bid) * (1 + (1 if delta > 0 else -1) * strategy.config.slippage_bps / 10000)
    strategy.fill(delta, price, stamp, f'paper-{len(strategy.fills) + 1}')
    strategy.completed({**action, 'average_fill': price})


def replay_path(bar, side):
    """Consume a known opening extreme once, before any intraminute entry.

    OHLC does not tell us whether an extreme was revisited. Do not invent a
    return to the opening high/low after the opposite extreme. The close may
    still cause a real modelled rebound. With neither extreme at the open,
    retain the explicitly disclosed adverse-first assumption.
    """
    if bar.open == bar.high:
        return [bar.open, bar.low, bar.close]
    if bar.open == bar.low:
        return [bar.open, bar.high, bar.close]
    return [bar.open, bar.low, bar.high, bar.close] if side > 0 else [bar.open, bar.high, bar.low, bar.close]


def replay(candles, settings, initial_side):
    """OHLC simulation: opening extreme first, otherwise adverse extreme first.

    This is an explicit approximation, not tick/bid-ask reconstruction.
    The initial entry candle uses only its close for post-entry decisions;
    its high/low cannot trigger exits, adds or trailing watermark changes.
    Only historical ladder reversals require close confirmation. Live/paper
    callers retain immediate reversals through action()'s default argument.
    Other orders keep the existing OHLC threshold simulation.
    """
    if not candles:
        raise ValueError('No completed candles available from the selected start time')
    price = candles[0].open
    quantity = settings.quantity if settings.sizing == 'quantity' else int(settings.capital / price)
    if quantity < 1:
        raise ValueError('Capital is too small to buy one share')
    strategy = Ladder(settings.model_dump(), initial_side, quantity)
    actions = []

    def execute_at_close(action, bar):
        action = {**action, 'execution': 'candle_close', 'candle_start': bar.start.isoformat()}
        paper_execute(strategy, action, bar.close, bar.close, bar.end.isoformat())
        strategy.fills[-1].update(execution='candle_close', candle_start=bar.start.isoformat())
        actions.append({'time': bar.end.isoformat(), **action})

    for index, bar in enumerate(candles):
        if strategy.done:
            break
        cutoff = bar.start.time() >= time.fromisoformat(settings.square_off)
        initial_entry_candle = not strategy.started
        action = strategy.action(bar.open, cutoff, allow_reversal=False)
        if action:
            paper_execute(strategy, action, bar.open, bar.open, bar.start.isoformat())
            actions.append({'time': bar.start.isoformat(), **action})
        if strategy.done:
            break
        can_open_at_close = (index + 1 < len(candles)
                             and bar.end.time() < time.fromisoformat(settings.square_off))
        if initial_entry_candle:
            # Do not infer a price path inside the entry minute, even when the
            # candle is green/red. Observe the close once, and fill there rather
            # than at an intraminute threshold that may have occurred earlier.
            close_action = strategy.action(
                bar.close, cutoff=bar.end.time() >= time.fromisoformat(settings.square_off),
                allow_reversal=can_open_at_close)
            if close_action and (can_open_at_close or close_action['desired'] == 0):
                execute_at_close(close_action, bar)
            continue
        # No future extrema are used to initialise this minute's trailing level.
        path = replay_path(bar, strategy.side)
        for origin, end in zip(path, path[1:]):
            cursor = origin
            for _ in range(200):
                if strategy.done:
                    break
                levels = [value for value in strategy.levels().values() if value is not None]
                if strategy.net_qty:
                    loss_price = strategy.average + (-settings.max_loss - strategy.realized + strategy.fees) / strategy.net_qty
                    if loss_price > 0:
                        levels.append(loss_price)
                # The current stop also includes the high/low watermark already visited.
                crossings = [level for level in levels if min(cursor, end) <= level <= max(cursor, end)
                             and abs(level - cursor) > 1e-8]
                point = min(crossings, key=lambda value: abs(value - cursor)) if crossings else end
                action = strategy.action(point, allow_reversal=False)
                if action:
                    paper_execute(strategy, action, point, point, bar.start.isoformat())
                    actions.append({'time': bar.start.isoformat(), **action})
                cursor = point
                if abs(cursor - end) < 1e-8:
                    break
            else:
                raise ValueError('Too many intraminute transitions; use wider risk settings')
        # Confirm against the closing price, using only the watermark already
        # observed. Execute once at close and never replay this candle's earlier
        # high/low against the new position. Do not open at the end of the data
        # or when scheduled square-off is already due.
        if not strategy.done and can_open_at_close:
            action = strategy.action(bar.close)
            if action and action['reason'] == 'reverse':
                execute_at_close(action, bar)
    if not strategy.done and strategy.net_qty:
        last = candles[-1]
        action = {'desired': 0, 'reason': 'end_of_data'}
        paper_execute(strategy, action, last.close, last.close, last.end.isoformat())
        actions.append({'time': last.end.isoformat(), **action})
    return {'strategy': asdict(strategy), 'actions': actions, 'pnl': strategy.realized - strategy.fees,
            'reversal_timing': 'candle_close',
            'entry_candle_checks': 'close_only',
            'model': 'Backtest-only candle-close reversals. Initial entry candle: use only its close for exits, trailing updates and adds; ignore its high/low. Close-triggered orders fill at close plus slippage. From the next candle, use OHLC, but reversals still require a close at or beyond SL/TSL. Opposite entry fills at that close and its checks begin next candle. Close fills use candle-end timestamps; other intraminute times identify candles, not exact seconds. Live/paper reversals remain immediate. OHLC order is assumed, not tick-accurate.'}
