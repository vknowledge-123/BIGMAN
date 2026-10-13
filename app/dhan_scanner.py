from __future__ import annotations

import csv
import json
import logging
import math
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .fno_symbols import FNO_SYMBOLS
from .daily_filter import apply_daily_volume_limit, calculate_daily_filter
from .schemas import VolumeFilterSettings
from .opening_filters import evaluate as evaluate_opening_filters, missing_history as missing_opening_history
from .opening_patterns import first_high_broken, retest_sequence
from .storage import DATA_DIR, ConfigStore

try:
    from dhanhq import DhanContext, MarketFeed, dhanhq
except Exception:  # pragma: no cover - handled at runtime for friendly UI errors.
    DhanContext = None
    MarketFeed = None
    dhanhq = None


LOGGER = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
SCRIP_MASTER_PATH = DATA_DIR / "api-scrip-master.csv"
SCRIP_INDEX_PATH = DATA_DIR / "nse-equity-instruments.json"
VOLUME_SAMPLE_COUNT = 3
BACKTEST_MAX_AGE_DAYS = 60
CIRCUIT_BANDS = (2.0, 5.0, 10.0, 20.0)
CIRCUIT_REFRESH_SECONDS = 60
HISTORY_REQUEST_SPACING = 0.23


def parse_symbols(raw: str) -> list[str]:
    seen: set[str] = set()
    symbols: list[str] = []
    for token in raw.replace(",", "\n").replace("\t", "\n").splitlines():
        symbol = token.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _extract_data(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and response.get("status") in {"success", "failure"}:
        if response.get("status") != "success":
            raise RuntimeError(_format_dhan_error(response.get("remarks")))
        data = response.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("Dhan API returned an empty response")
        return data
    if isinstance(response, dict):
        return response
    raise RuntimeError("Unexpected Dhan API response")


def _format_dhan_error(remarks: Any) -> str:
    if isinstance(remarks, dict):
        code = remarks.get("error_code")
        error_type = remarks.get("error_type")
        message = remarks.get("error_message")
        parts = [str(item) for item in (error_type, code) if item]
        prefix = " ".join(parts)
        if prefix and message:
            return f"{prefix}: {message}"
        return prefix or str(remarks)
    return str(remarks or "Dhan API request failed")


def _should_stop_api_batch(error: Exception | str) -> bool:
    message = str(error)
    return any(
        marker in message
        for marker in ("DH-901", "Invalid_Authentication", "DH-904", "Rate_Limit")
    )


@dataclass
class Instrument:
    symbol: str
    security_id: str
    name: str
    exchange_segment: str = "NSE_EQ"
    instrument_type: str = "EQUITY"


@dataclass
class Candle:
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=1)

    @property
    def turnover(self) -> float:
        return self.volume * self.close

    @property
    def color(self) -> str:
        if self.close > self.open:
            return "green"
        if self.close < self.open:
            return "red"
        return "doji"

    def update(self, price: float, volume_delta: int) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += max(volume_delta, 0)


@dataclass
class OpeningSignal:
    first_label: str
    first: Candle
    second_label: str
    second: Candle | None
    volume_average: float | None
    volume_multiplier: float | None
    colors_match: bool
    possible_candidate: bool
    reason: str


@dataclass
class StockState:
    instrument: Instrument
    previous_close: float | None = None
    ltp: float | None = None
    percent_change: float | None = None
    day_volume: int | None = None
    last_cumulative_volume: int | None = None
    current_candle: Candle | None = None
    completed_candle: Candle | None = None
    last_tick_time: datetime | None = None
    last_tick_received_at: datetime | None = None
    opening_volume_average: float | None = None
    opening_volume_samples: list[dict[str, Any]] = field(default_factory=list)
    opening_candles: list[Candle] = field(default_factory=list)
    today_opening_volume: int | None = None
    volume_multiplier: float | None = None
    opening_colors_match: bool = False
    possible_candidate: bool = False
    redwala_gira: bool = False
    qualifies_scan: bool = False
    daily_filter: dict[str, Any] | None = None
    signal_session: date | None = None
    opening_pair_confirmed: bool = False
    confirmed_opening_candle: Candle | None = None
    confirmed_session_candles: dict[datetime, Candle] = field(default_factory=dict)
    post_opening_trough: float | None = None
    post_opening_trough_session: date | None = None
    post_opening_peak: float | None = None
    post_opening_peak_session: date | None = None
    retest_break: bool = False
    retest_break_at: str | None = None
    retest_status: str = "waiting"
    retest_reason: str | None = None
    retest_attempt_at: datetime | None = None
    retest_checked_through: datetime | None = None
    volume_session: date | None = None
    preparation_status: str = "unresolved"
    confirmation_status: str = "pending"
    opening_metadata_pending: bool = False
    provisional_setup: str | None = None
    feed_baseline_session: date | None = None
    feed_incomplete: bool = True
    opening_first_tick: datetime | None = None
    opening_last_tick: datetime | None = None
    opening_boundary_seen: bool = False
    feed_baseline_volume: int | None = None
    opening_boundary_volume: int | None = None
    upper_circuit_limit: float | None = None
    lower_circuit_limit: float | None = None
    circuit_fetched_at: datetime | None = None
    circuit_attempt_at: datetime | None = None
    circuit_error: str | None = None
    candidate_reason: str | None = None
    status: str = "waiting"
    error: str | None = None


class InstrumentResolver:
    def __init__(self, csv_path: Path = SCRIP_MASTER_PATH, index_path: Path | None = None) -> None:
        self.csv_path = csv_path
        self.index_path = index_path or (SCRIP_INDEX_PATH if csv_path == SCRIP_MASTER_PATH else csv_path.with_suffix(".nse-equity.json"))

    def ensure_master(self, max_age_hours: int = 24) -> None:
        should_download = not self.csv_path.exists()
        if not should_download:
            modified_at = datetime.fromtimestamp(self.csv_path.stat().st_mtime, IST)
            should_download = datetime.now(IST) - modified_at > timedelta(hours=max_age_hours)
        if should_download:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            response = requests.get(SCRIP_MASTER_URL, timeout=60)
            response.raise_for_status()
            tmp_path = self.csv_path.with_suffix(".tmp")
            tmp_path.write_bytes(response.content)
            tmp_path.replace(self.csv_path)

    def resolve(self, symbols: list[str]) -> tuple[dict[str, Instrument], list[str]]:
        self.ensure_master()
        index = self._load_index()
        resolved: dict[str, Instrument] = {}
        unresolved: list[str] = []
        for symbol in symbols:
            item = index.get(symbol)
            if not item:
                unresolved.append(symbol)
                continue
            resolved[symbol] = Instrument(
                symbol=symbol,
                security_id=str(item["security_id"]),
                name=item.get("name") or symbol,
            )
        return resolved, unresolved

    def _load_index(self) -> dict[str, dict[str, str]]:
        if self._index_is_fresh():
            return json.loads(self.index_path.read_text(encoding="utf-8"))

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        index: dict[str, dict[str, str]] = {}
        priority_by_symbol: dict[str, int] = {}
        series_priority = {"EQ": 0, "BE": 1, "SM": 2, "ST": 3}
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                symbol = row.get("SEM_TRADING_SYMBOL", "").strip().upper()
                if row.get("SEM_EXM_EXCH_ID", "").strip().upper() != "NSE":
                    continue
                if row.get("SEM_SEGMENT", "").strip().upper() != "E":
                    continue
                if row.get("SEM_INSTRUMENT_NAME", "").strip().upper() != "EQUITY":
                    continue
                priority = series_priority.get(row.get("SEM_SERIES", "").upper(), 99)
                if symbol in index and priority >= priority_by_symbol[symbol]:
                    continue
                index[symbol] = {
                    "security_id": str(row["SEM_SMST_SECURITY_ID"]),
                    "name": row.get("SM_SYMBOL_NAME") or row.get("SEM_CUSTOM_SYMBOL") or symbol,
                }
                priority_by_symbol[symbol] = priority

        tmp_path = self.index_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
        tmp_path.replace(self.index_path)
        return index

    def _index_is_fresh(self) -> bool:
        if not self.index_path.exists() or not self.csv_path.exists():
            return False
        return self.index_path.stat().st_mtime >= self.csv_path.stat().st_mtime


class ScannerEngine:
    def __init__(self, store: ConfigStore) -> None:
        self.store = store
        self.resolver = InstrumentResolver()
        self._lock = threading.RLock()
        self._history_lock = threading.Lock()
        self._history_condition = threading.Condition()
        self._priority_workers = 0
        self._request_context = threading.local()
        self._volume_filters = store.load().volume_filters
        self._settings_lock = threading.Lock()
        self._opening_finished = True
        self._preparation_lock = threading.Lock()
        self._security_symbols: dict[str, str] = {}
        self._last_history_call = 0.0
        self._quote_lock = threading.Lock()
        self._last_quote_call = 0.0
        self._circuit_refresh_lock = threading.Lock()
        self._circuit_thread: threading.Thread | None = None
        self._states: dict[str, StockState] = {}
        self._unresolved_symbols: list[str] = []
        self._feed: Any = None
        self._feed_thread: threading.Thread | None = None
        self._candidate_thread: threading.Thread | None = None
        self._candidate_stop = threading.Event()
        self._candidate_refresh = threading.Event()
        self._subscription_refresh = threading.Event()
        self._subscribed_symbols: set[str] = set()
        self._running = False
        self._connected = False
        self._status = "Idle"

    def load_saved(self) -> None:
        config = self.store.load()
        self._volume_filters = config.volume_filters
        if config.symbols:
            try:
                self.prepare_symbols(config.symbols)
            except Exception as exc:
                with self._lock:
                    self._states = {}
                    self._unresolved_symbols = config.symbols
                    self._status = f"Could not load saved symbols: {exc}"
                return

    def prepare_symbols(self, symbols: list[str]) -> list[str]:
        resolved, unresolved = self.resolver.resolve(symbols)
        config = self.store.load()
        session = datetime.now(IST).date()
        was_running = self._running
        if was_running:
            self.stop()
        with self._lock:
            previous = self._states
            self._states = {}
            for symbol, instrument in resolved.items():
                state = previous.get(symbol)
                if state and self._daily_ready(state, session):
                    self._states[symbol] = state
                    continue
                entry = config.opening_volume_cache.get(symbol, {})
                daily = apply_daily_volume_limit(entry.get("daily_filter"), self.volume_filters.daily_volume_max)
                volume_day = entry.get("volume_session") or str(entry.get("cached_at", ""))[:10]
                average = _float_or_none(entry.get("average"))
                fresh = (volume_day == session.isoformat() and average is not None and average > 0
                         and len(entry.get("samples", [])) == 3)
                state = StockState(instrument=instrument, previous_close=config.previous_closes.get(symbol),
                                   daily_filter=daily,
                                   opening_volume_average=_float_or_none(entry.get("average")) if fresh else None,
                                   opening_volume_samples=list(entry.get("samples", [])) if fresh else [],
                                   volume_session=session if fresh else None)
                if self._daily_ready(state, session):
                    state.previous_close = daily["previous_close"]
                    state.preparation_status = ("excluded" if not daily["passes"] else
                                                "ready" if self._volume_ready(state, session) else "needs_volume")
                    if not daily["passes"]:
                        state.confirmation_status = "pending"
                        state.signal_session = session
                self._states[symbol] = state
            self._security_symbols = {state.instrument.security_id: symbol for symbol, state in self._states.items()}
            self._unresolved_symbols = unresolved
            self._status = f"Loaded {len(resolved)} symbol(s)" + ("; restart Live for the updated list" if was_running else "")
        return unresolved

    @property
    def volume_filters(self) -> VolumeFilterSettings:
        return getattr(self._request_context, "volume_filters", self._volume_filters)

    def update_volume_filters(self, settings: VolumeFilterSettings) -> str:
        with self._settings_lock:
            self.store.update_volume_filters(settings)
            session = datetime.now(IST).date()
            with self._lock:
                self._volume_filters = settings
                for state in self._states.values():
                    state.retest_break = False
                    state.retest_status = "waiting"
                    state.retest_break_at = None
                    state.retest_attempt_at = None
                    state.retest_reason = None
                    state.daily_filter = apply_daily_volume_limit(state.daily_filter, settings.daily_volume_max)
                    state.possible_candidate = state.redwala_gira = state.retest_break = state.qualifies_scan = False
                    state.provisional_setup = None
                    state.confirmation_status = "pending"
                    state.candidate_reason = None
                    state.status = "Filters updated; awaiting opening check"
                    state.preparation_status = "unresolved"
                    if self._daily_ready(state, session):
                        state.preparation_status = ("excluded" if not state.daily_filter["passes"] else
                                                    "ready" if self._volume_ready(state, session) else "needs_volume")
                        if not state.daily_filter["passes"]:
                            state.status = "Daily filter failed for Candidates/Retest; Redwala still checked"
                    first = state.confirmed_opening_candle
                    if first and first.start.date() == session:
                        self._apply_opening_candidate(state.instrument.symbol, [first])
                # Cached raw inputs remain valid. Derived decisions are recalculated
                # on load; do not rewrite the entire cache while holding the feed lock.
                was_running = self._running
                if was_running:
                    self._candidate_refresh.set()
                    self._subscription_refresh.set()
            message = (f"Filters saved: previous day <= {settings.daily_volume_max:g}x "
                       f"or price change <= +1%; first minute >= {settings.minute_volume_min:g}x; "
                       f"first-candle turnover > INR {settings.first_candle_turnover_min / 10_000_000:g} crore. "
                       f"Today Open Cross {'ON' if settings.today_open_cross else 'OFF'}. "
                       f"Monthly Filter {'ON' if settings.monthly_filter else 'OFF'}; "
                       f"Last 2 Days Filter {'ON' if settings.last_two_days_filter else 'OFF'}. "
                       "Applied to Live and future backtests.")
            if was_running:
                message += " Live connection kept running; missing data is checked in the background."
            else:
                message += " Cache Volume + Day Levels prepares any newly eligible stocks."
            return message

    def _refresh_filter_subscriptions(self, feed: Any, stop_event: threading.Event,
                                      refresh_event: threading.Event) -> None:
        # A slow Dhan send must never hold the state lock or a Save & Apply request.
        # One worker coalesces repeated edits and reads the latest eligibility.
        while not stop_event.is_set():
            if not refresh_event.wait(0.25):
                continue
            refresh_event.clear()
            with self._lock:
                if stop_event.is_set() or feed is not self._feed or not self._running:
                    return
                session = datetime.now(IST).date()
                additions = [state for symbol, state in self._states.items()
                             if symbol not in self._subscribed_symbols]
            if not additions:
                continue
            try:
                feed.subscribe_symbols([(MarketFeed.NSE, state.instrument.security_id, MarketFeed.Quote)
                                        for state in additions])
                with self._lock:
                    if feed is self._feed and not stop_event.is_set():
                        self._subscribed_symbols.update(state.instrument.symbol for state in additions)
            except Exception as exc:
                with self._lock:
                    if feed is self._feed and not stop_event.is_set():
                        self._status = f"Filters applied; live subscription update failed: {exc}. Save again to retry."

    def credentials_ready(self) -> bool:
        config = self.store.load()
        return bool(config.client_id and config.access_token)

    def _client(self) -> Any:
        if DhanContext is None or dhanhq is None:
            raise RuntimeError("dhanhq SDK is not installed. Run: py -m pip install -r requirements.txt")
        config = self.store.load()
        if not config.client_id or not config.access_token:
            raise RuntimeError("Save Dhan client ID and access token first")
        return dhanhq(DhanContext(config.client_id, config.access_token))

    def cache_previous_closes(self) -> dict[str, float]:
        client = self._client()
        today = datetime.now(IST).date()
        from_date = (today - timedelta(days=14)).isoformat()
        to_date = today.isoformat()
        cached: dict[str, float] = {}
        errors: dict[str, str] = {}

        with self._lock:
            states = list(self._states.values())

        skip_historical_fallback = False
        try:
            cached.update(self._cache_from_ohlc_batch(client, states))
        except Exception as exc:
            LOGGER.warning("Batch OHLC previous close cache failed: %s", exc)
            skip_historical_fallback = _should_stop_api_batch(exc)
            with self._lock:
                self._status = f"Batch cache failed, trying historical fallback: {exc}"
                if skip_historical_fallback:
                    self._status = f"Dhan rejected the cache request: {exc}"
                    for state in states:
                        state.error = str(exc)
                        state.status = "rate limited"
                    return cached

        for state in states:
            symbol = state.instrument.symbol
            if symbol in cached or skip_historical_fallback:
                continue
            try:
                response = self._historical_daily_with_retry(
                    client,
                    state.instrument.security_id,
                    state.instrument.exchange_segment,
                    state.instrument.instrument_type,
                    from_date,
                    to_date,
                )
                data = _extract_data(response)
                closes = data.get("close") or []
                if not closes:
                    raise RuntimeError("No daily close returned")
                close = _float_or_none(closes[-1])
                if close is None:
                    raise RuntimeError("Invalid previous close returned")
                cached[symbol] = close
                with self._lock:
                    self._states[symbol].previous_close = close
                    self._states[symbol].error = None
                    self._states[symbol].status = "cached"
            except Exception as exc:
                errors[symbol] = str(exc)
                with self._lock:
                    self._states[symbol].error = str(exc)
                    self._states[symbol].status = "cache error"

        if cached:
            self.store.update_previous_closes(cached)

        with self._lock:
            self._status = f"Cached previous close for {len(cached)} stock(s)"
            if errors:
                self._status += f"; {len(errors)} error(s)"
        return cached

    def _daily_ready(self, state: StockState, session: date) -> bool:
        daily = state.daily_filter
        return bool(daily and daily.get("session_date") == session.isoformat()
                    and "previous_high" in daily and "previous_low" in daily)

    @staticmethod
    def _five_day_close_level(daily: dict | None, session: date) -> float | None:
        if not daily or daily.get("session_date") != session.isoformat():
            return None
        samples = daily.get("five_day_closes") or []
        if len(samples) != 5:
            return None
        dates = [item.get("date", "") for item in samples]
        prices = [_float_or_none(item.get("close")) for item in samples]
        if (len(set(dates)) != 5 or any(not day or day >= session.isoformat() for day in dates)
                or any(price is None or price <= 0 for price in prices)):
            return None
        return max(prices)

    @staticmethod
    def _volume_ready(state: StockState, session: date) -> bool:
        return bool(state.volume_session == session and state.opening_volume_average
                    and state.opening_volume_average > 0 and len(state.opening_volume_samples) == 3)

    def _cache_entry(self, state: StockState) -> dict:
        return {"average": state.opening_volume_average, "samples": state.opening_volume_samples,
                "required_opening_volume": self.volume_filters.minute_volume_min * state.opening_volume_average if state.opening_volume_average else None,
                "volume_session": state.volume_session.isoformat() if state.volume_session else None,
                "daily_filter": state.daily_filter, "cached_at": datetime.now(IST).isoformat(timespec="seconds")}

    def _prepare_daily(self, client: Any, state: StockState, session: date, *, need_five: bool = False) -> None:
        fetched = not self._daily_ready(state, session)
        first = state.confirmed_opening_candle
        # Optional opening history must not block Redwala or shared volume preparation.
        need_opening_history = need_five or bool(first and first.start.date() == session and first.color == "green")
        if need_opening_history and missing_opening_history(state.daily_filter, session, self.volume_filters):
            fetched = True
        if need_five and self._five_day_close_level(state.daily_filter, session) is None:
            fetched = True
        # Five-close history is an additional requirement only for green setups.
        # Never hold up Redwala (or its volume preparation) for that history.
        if (self.volume_filters.today_open_cross and first and first.start.date() == session
                and first.color == "green" and state.daily_filter and state.daily_filter.get("passes")
                and self._five_day_close_level(state.daily_filter, session) is None):
            fetched = True
        if fetched:
            daily = self._fetch_daily_filter(client, state.instrument, session)
            with self._lock:
                state.daily_filter = daily
        with self._lock:
            state.daily_filter = apply_daily_volume_limit(state.daily_filter, self.volume_filters.daily_volume_max)
            state.previous_close = state.daily_filter["previous_close"]
            if state.ltp is not None and state.previous_close:
                state.percent_change = (state.ltp / state.previous_close - 1) * 100
            if not state.daily_filter["passes"]:
                state.preparation_status = "excluded"
                state.confirmation_status = "pending"
                state.signal_session = session
                state.possible_candidate = state.retest_break = False
                state.redwala_gira = bool(state.redwala_gira and state.confirmed_opening_candle
                                         and state.confirmed_opening_candle.start.date() == session)
                state.qualifies_scan = state.redwala_gira
                state.status = "Daily filter failed for Candidates/Retest; Redwala still checked"
            else:
                state.preparation_status = "ready" if self._volume_ready(state, session) else "needs_volume"
            state.error = None

        if fetched:
            self.store.update_opening_volume_cache({state.instrument.symbol: self._cache_entry(state)})
        missing = missing_opening_history(state.daily_filter, session, self.volume_filters)
        if need_opening_history and state.daily_filter["passes"] and missing:
            state.preparation_status = "unresolved"
            raise RuntimeError(missing)

    def _prepare_volume(self, client: Any, state: StockState, session: date,
                        stop_event: threading.Event | None = None) -> None:
        if self._volume_ready(state, session):
            state.preparation_status = "ready"
            return
        samples, today_candles = self._fetch_opening_volume_history(client, state.instrument)
        with self._lock:
            if ((stop_event and stop_event.is_set())
                    or self._states.get(state.instrument.symbol) is not state):
                return
            state.opening_volume_samples = samples
            state.opening_volume_average = sum(sample["volume"] for sample in samples) / len(samples)
            state.volume_session = session
            state.preparation_status = "ready"
            state.error = None
            state.status = "volume cached"
            if self._first_opening_candle(today_candles) is not None:
                self._apply_opening_candidate(state.instrument.symbol, today_candles)

    def cache_opening_volume_averages(self) -> dict[str, float]:
        with self._preparation_lock:
            return self._prepare_scan_universe()

    def _prepare_scan_universe(self) -> dict[str, float]:
        client = self._client()
        session = datetime.now(IST).date()
        with self._lock:
            states = list(self._states.values())
        if not states:
            raise RuntimeError("Add stocks first")
        fatal_error = None
        # Complete daily filtering for the entire universe before minute-history work.
        for stage in ("daily", "volume"):
            pending = list(states)
            for attempt in range(3):
                if not pending or fatal_error:
                    break
                retry = []
                for index, state in enumerate(pending):
                    try:
                        if stage == "daily":
                            self._prepare_daily(client, state, session)
                        elif self._daily_ready(state, session) and state.daily_filter["passes"]:
                            self._prepare_volume(client, state, session)
                        else:
                            continue
                    except Exception as exc:
                        with self._lock:
                            state.preparation_status = "unresolved"
                            state.status = "Preparation unresolved"
                            state.error = str(exc)
                            state.possible_candidate = state.retest_break = False
                            state.redwala_gira = bool(state.redwala_gira and state.confirmed_opening_candle
                                                     and state.confirmed_opening_candle.start.date() == session)
                            state.qualifies_scan = state.redwala_gira
                        retry.append(state)
                        if _should_stop_api_batch(exc):
                            fatal_error = str(exc)
                            for remaining in pending[index + 1:]:
                                remaining.preparation_status = "unresolved"
                                remaining.status = "volume cache skipped"
                                remaining.error = f"Skipped after Dhan error: {exc}"
                                remaining.possible_candidate = remaining.retest_break = False
                                remaining.redwala_gira = bool(remaining.redwala_gira and remaining.confirmed_opening_candle
                                                             and remaining.confirmed_opening_candle.start.date() == session)
                                remaining.qualifies_scan = remaining.redwala_gira
                                remaining.provisional_setup = None
                            break
                    with self._lock:
                        self._status = f"Preparing {stage}: {index + 1}/{len(pending)} (pass {attempt + 1})"
                pending = retry
            self.store.update_opening_volume_cache({state.instrument.symbol: self._cache_entry(state) for state in states})
            if fatal_error:
                break
        closes = {state.instrument.symbol: state.previous_close for state in states
                  if self._daily_ready(state, session) and state.previous_close}
        if closes:
            self.store.update_previous_closes(closes)
        cached = {state.instrument.symbol: state.opening_volume_average for state in states
                  if state.preparation_status == "ready" and self._volume_ready(state, session)}
        excluded = sum(state.preparation_status == "excluded" for state in states)
        unresolved = sum(state.preparation_status == "unresolved" for state in states)
        with self._lock:
            self._status = f"Prepared {len(cached)}; daily filter excluded {excluded}; unresolved {unresolved}"
        if not cached and fatal_error:
            raise RuntimeError(fatal_error)
        self.refresh_circuit_limits(client)
        return cached

    def _fetch_opening_volume_history(
        self,
        client: Any,
        instrument: Instrument,
    ) -> tuple[list[dict[str, Any]], list[Candle]]:
        now = datetime.now(IST)
        all_candles: dict[datetime, Candle] = {}
        cursor_end = now

        for _ in range(6):
            window_start = cursor_end - timedelta(days=9)
            response = self._intraday_with_retry(
                client,
                instrument.security_id,
                instrument.exchange_segment,
                instrument.instrument_type,
                window_start.strftime("%Y-%m-%d %H:%M:%S"),
                cursor_end.strftime("%Y-%m-%d %H:%M:%S"),
            )
            for candle in self._parse_intraday_candles(response):
                all_candles[candle.start] = candle

            samples = self._select_historical_opening_samples(
                list(all_candles.values()), now.date(), VOLUME_SAMPLE_COUNT
            )
            if len(samples) == VOLUME_SAMPLE_COUNT:
                today_candles = [
                    candle
                    for candle in all_candles.values()
                    if candle.start.date() == now.date() and candle.end <= now
                ]
                return samples, today_candles
            cursor_end = window_start

        raise RuntimeError(
            f"Only {len(samples)} valid prior opening candle(s) found; 3 are required"
        )

    def _select_historical_opening_samples(
        self,
        candles: list[Candle],
        before_date: date,
        count: int,
    ) -> list[dict[str, Any]]:
        by_date: dict[date, list[Candle]] = {}
        for candle in sorted(candles, key=lambda item: item.start):
            if candle.start.date() < before_date:
                by_date.setdefault(candle.start.date(), []).append(candle)

        trading_dates = sorted(by_date)
        samples: list[dict[str, Any]] = []
        for trading_date in reversed(trading_dates):
            opening = self._first_opening_candle(by_date[trading_date])
            if opening is None or opening.volume <= 0:
                continue

            previous_dates = [item for item in trading_dates if item < trading_date]
            previous_close = by_date[previous_dates[-1]][-1].close if previous_dates else None
            if self._looks_like_opening_circuit(opening, previous_close):
                continue

            samples.append(
                {
                    "date": trading_date.isoformat(),
                    "candle_start": opening.start.strftime("%H:%M"),
                    "volume": opening.volume,
                }
            )
            if len(samples) == count:
                break
        return samples

    @staticmethod
    def _first_opening_candle(candles: list[Candle]) -> Candle | None:
        by_minute = {candle.start.strftime("%H:%M"): candle for candle in candles}
        return by_minute.get("09:14") or by_minute.get("09:15")

    @staticmethod
    def _looks_like_opening_circuit(candle: Candle, previous_close: float | None) -> bool:
        if not previous_close:
            return False
        tolerance = max(abs(candle.open), 1.0) * 0.000001
        price_locked = candle.high - candle.low <= tolerance
        if not price_locked:
            return False
        gap_percent = abs((candle.open - previous_close) / previous_close * 100)
        return any(abs(gap_percent - band) <= 0.35 for band in CIRCUIT_BANDS)

    def _fetch_daily_filter(self, client: Any, instrument: Instrument, target_date: date) -> dict:
        response = self._historical_daily_with_retry(
            client,
            instrument.security_id,
            instrument.exchange_segment,
            instrument.instrument_type,
            (target_date - timedelta(days=90)).isoformat(),
            target_date.isoformat(),
        )
        try:
            return calculate_daily_filter(_extract_data(response), target_date, self.volume_filters.daily_volume_max)
        except (RuntimeError, ValueError) as exc:
            raise RuntimeError(f"Daily history for {instrument.symbol} (security ID {instrument.security_id}, "
                               f"{target_date - timedelta(days=90)} to {target_date}, end exclusive): {exc}") from exc

    def _qualify_signal(self, signal: OpeningSignal, daily_filter: dict | None, session: date) -> dict:
        daily_filter = apply_daily_volume_limit(daily_filter, self.volume_filters.daily_volume_max)
        daily_ready = bool(daily_filter and daily_filter.get("session_date") == session.isoformat())
        daily_pass = daily_ready and daily_filter.get("passes") is True
        volume_pass = signal.volume_multiplier is not None and signal.volume_multiplier >= self.volume_filters.minute_volume_min
        turnover_min = self.volume_filters.first_candle_turnover_min
        turnover_pass = math.isfinite(signal.first.turnover) and signal.first.turnover > turnover_min
        open_cross_level = self._five_day_close_level(daily_filter, session)
        open_cross_pass = (not self.volume_filters.today_open_cross
                           or (open_cross_level is not None and signal.first.open > open_cross_level))
        opening_checks = evaluate_opening_filters(daily_filter, session, signal.first.open, self.volume_filters)
        first_red = signal.first.color == "red"
        open_high = signal.first.open == signal.first.high
        possible = bool(volume_pass and turnover_pass and daily_pass and open_cross_pass and opening_checks["passes"] and signal.first.color == "green")
        redwala = bool(turnover_pass and first_red and open_high)
        reason = (f"{signal.reason}; first candle turnover {signal.first.turnover:,.2f} INR "
                  f"> {turnover_min:,.2f} INR ({'pass' if turnover_pass else 'fail'})")
        if signal.first.color == "green" and opening_checks["reason"]:
            reason += "; " + opening_checks["reason"]
        if self.volume_filters.today_open_cross and signal.first.color == "green":
            if open_cross_level is None:
                reason += "; Today Open Cross unresolved: five completed trading-session closes unavailable"
            else:
                reason += (f"; Today Open Cross: first open {signal.first.open:g} > "
                           f"previous 5-session highest close {open_cross_level:g} ({'pass' if open_cross_pass else 'fail'})")
        if not daily_ready:
            reason += "; previous-day volume check unavailable for this session"
        else:
            reason += (
                f"; {daily_filter['previous_date']} daily volume {daily_filter['multiplier']:.2f}x"
                f" (limit <= {self.volume_filters.daily_volume_max:g}x or price change <= +1%)"
                f", close change {daily_filter['percent_change']:.2f}%"
                f" ({'pass' if daily_pass else 'fail'})"
            )
        if first_red:
            reason += f"; first candle Open = High: {'yes' if open_high else 'no'}"
            if open_high:
                reason = (f"Redwala: first candle red, Open = High; turnover {signal.first.turnover:,.2f} INR "
                          f"> {turnover_min:,.2f} INR ({'pass' if turnover_pass else 'fail'}); "
                          "daily and minute volume filters do not apply")
        return {
            "possible_candidate": possible,
            "redwala_gira": redwala,
            "retest_base_eligible": bool(volume_pass and turnover_pass and daily_pass and first_red),
            "retest_eligible": bool(volume_pass and turnover_pass and daily_pass and first_red and open_cross_pass and opening_checks["passes"]),
            "qualifies_scan": possible or redwala,
            "first_open_equals_high": open_high,
            "first_open_equals_low": signal.first.open == signal.first.low,
            **ScannerEngine._previous_day_crosses(signal.first, daily_filter, session, possible, redwala),
            "candidate_reason": reason,
        }

    @staticmethod
    def _previous_day_crosses(first: Candle | None, daily_filter: dict | None,
                             session: date | None, possible: bool, redwala: bool) -> dict:
        high_cross = low_cross = False
        if first and daily_filter and session == first.start.date() and daily_filter.get("session_date") == session.isoformat():
            high = _float_or_none(daily_filter.get("previous_high"))
            low = _float_or_none(daily_filter.get("previous_low"))
            high_cross = bool(possible and high is not None and high > 0 and first.open < high < first.close)
            low_cross = bool(redwala and low is not None and low > 0 and first.close < low < first.open)
        return {"previous_day_high_cross": high_cross, "previous_day_low_cross": low_cross}

    @staticmethod
    def _second_candle_pdl_cross(first: Candle | None, candles: list[Candle],
                                 daily: dict | None, session: date | None, redwala: bool) -> bool:
        if not redwala or not first or first.start.date() != session:
            return False
        second = next((bar for bar in candles if bar.start == first.end), None)
        if second is None or second.end > datetime.now(IST):
            return False
        return ScannerEngine._previous_day_crosses(second, daily, session, False, True)["previous_day_low_cross"]

    def backtest_date(self, target_date: date, scan_type: str = "opening") -> dict[str, Any]:
        # One run uses one immutable settings snapshot even if Live settings change.
        previous = getattr(self._request_context, "volume_filters", None)
        self._request_context.volume_filters = self._volume_filters
        try:
            return self._backtest_date(target_date, scan_type)
        finally:
            if previous is None:
                del self._request_context.volume_filters
            else:
                self._request_context.volume_filters = previous

    def _backtest_date(self, target_date: date, scan_type: str = "opening") -> dict[str, Any]:
        if scan_type != "opening":
            raise ValueError("Unknown scan type")
        today = datetime.now(IST).date()
        earliest = today - timedelta(days=BACKTEST_MAX_AGE_DAYS)
        if target_date > today:
            raise ValueError("Backtest date cannot be in the future")
        if target_date < earliest:
            raise ValueError(
                f"Backtest date must be within the last {BACKTEST_MAX_AGE_DAYS} days"
            )

        with self._lock:
            states = list(self._states.values())
        if not states:
            raise ValueError("Add stocks before running a backtest")

        client = self._client()
        rows: list[dict[str, Any]] = []
        completed_count = 0
        first_error: str | None = None
        for index, state in enumerate(states):
            try:
                candles = self._fetch_backtest_history(client, state.instrument, target_date)
                daily_error = None
                try:
                    daily_filter = self._fetch_daily_filter(client, state.instrument, target_date)
                except Exception as exc:
                    first = self._first_opening_candle([bar for bar in candles if bar.start.date() == target_date])
                    if not (first and first.color == "red" and first.open == first.high):
                        raise
                    daily_filter = None
                    daily_error = str(exc)
                row = self._build_backtest_row(state.instrument, target_date, candles, daily_filter)
                if daily_error:
                    row["data_warning"] = daily_error + "; daily filters and previous-day levels unavailable. Redwala uses turnover only."
                    row["status"] = "Partial: daily history unavailable"
                rows.append(row)
                if daily_error and _should_stop_api_batch(daily_error):
                    rows.extend(self._backtest_error_row(remaining.instrument, target_date,
                                f"Skipped after Dhan error: {daily_error}") for remaining in states[index + 1:])
                    break
                completed_count += 1
            except Exception as exc:
                first_error = first_error or str(exc)
                rows.append(self._backtest_error_row(state.instrument, target_date, str(exc)))
                if _should_stop_api_batch(exc):
                    for remaining in states[index + 1 :]:
                        rows.append(
                            self._backtest_error_row(
                                remaining.instrument,
                                target_date,
                                f"Skipped after Dhan error: {exc}",
                            )
                        )
                    break

        if states and completed_count == 0 and first_error and _should_stop_api_batch(first_error):
            raise RuntimeError(first_error)

        rows.sort(
            key=lambda row: (
                row["possible_candidate"],
                row["volume_multiplier"] if row["volume_multiplier"] is not None else -1,
            ),
            reverse=True,
        )
        return {
            "scan_type": scan_type,
            "target_date": target_date.isoformat(),
            "volume_filters": self.volume_filters.model_dump(),
            "stocks": rows,
            "tested_count": sum(row["error"] is None for row in rows),
            "four_x_count": sum(
                row["volume_multiplier"] is not None
                and row["volume_multiplier"] >= self.volume_filters.minute_volume_min
                for row in rows
            ),
            "candidate_count": sum(row["possible_candidate"] for row in rows),
            "qualified_count": sum(row.get("qualifies_scan", False) for row in rows),
            "redwala_count": sum(row.get("redwala_gira", False) for row in rows),
            "retest_count": sum(row.get("retest_break", False) for row in rows),
            "error_count": sum(row["error"] is not None for row in rows),
            "warning_count": sum(bool(row.get("data_warning")) for row in rows),
        }


    def _fetch_backtest_history(
        self,
        client: Any,
        instrument: Instrument,
        target_date: date,
    ) -> list[Candle]:
        range_start = datetime.combine(
            target_date - timedelta(days=BACKTEST_MAX_AGE_DAYS),
            dt_time.min,
            tzinfo=IST,
        )
        range_end = datetime.combine(target_date + timedelta(days=1), dt_time.min, tzinfo=IST)
        response = self._intraday_with_retry(
            client,
            instrument.security_id,
            instrument.exchange_segment,
            instrument.instrument_type,
            range_start.strftime("%Y-%m-%d %H:%M:%S"),
            range_end.strftime("%Y-%m-%d %H:%M:%S"),
        )
        try:
            return [bar for bar in self._parse_intraday_candles(response) if bar.end <= datetime.now(IST)]
        except (RuntimeError, ValueError) as exc:
            raise RuntimeError(f"Minute history for {instrument.symbol} (security ID {instrument.security_id}, "
                               f"{range_start:%Y-%m-%d %H:%M:%S} to {range_end:%Y-%m-%d %H:%M:%S}): {exc}") from exc

    def _build_backtest_row(
        self,
        instrument: Instrument,
        target_date: date,
        candles: list[Candle],
        daily_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        samples = self._select_historical_opening_samples(
            candles, target_date, VOLUME_SAMPLE_COUNT
        )
        first = self._first_opening_candle([bar for bar in candles if bar.start.date() == target_date])
        if len(samples) != VOLUME_SAMPLE_COUNT and not (first and first.color == "red" and first.open == first.high):
            raise RuntimeError(
                f"Only {len(samples)} valid prior opening candle(s) found; 3 are required"
            )

        target_candles = [candle for candle in candles if candle.start.date() == target_date]
        if not target_candles:
            raise RuntimeError("No intraday data returned for the selected date")

        average = sum(sample["volume"] for sample in samples) / len(samples) if len(samples) == VOLUME_SAMPLE_COUNT else None
        daily_filter = apply_daily_volume_limit(daily_filter, self.volume_filters.daily_volume_max)
        signal = self._calculate_opening_signal(target_candles, average)
        missing = missing_opening_history(daily_filter, target_date, self.volume_filters)
        if missing and signal.first.color == "green":
            raise RuntimeError(missing)
        if (self.volume_filters.today_open_cross and signal.first.color == "green"
                and self._five_day_close_level(daily_filter, target_date) is None):
            raise RuntimeError("Today Open Cross needs five completed trading-session closes; daily history is incomplete")
        qualification = self._qualify_signal(signal, daily_filter, target_date)
        now = datetime.now(IST)
        completed = [bar for bar in target_candles if target_date < now.date() or bar.end <= now]
        pattern = self._retest_result(signal.first, completed, daily_filter, qualification)
        qualification["qualifies_scan"] = qualification["qualifies_scan"] or pattern["retest_break"]
        return {
            **pattern,
            **self._redwala_breaks(signal.first, completed, daily_filter, qualification["redwala_gira"]),
            "previous_day_low_cross_second_candle": self._second_candle_pdl_cross(
                signal.first, completed, daily_filter, target_date, qualification["redwala_gira"]),
            "first_candle_high_break": bool(qualification["possible_candidate"] and first_high_broken(signal.first, completed)),
            "symbol": instrument.symbol,
            "name": instrument.name,
            "security_id": instrument.security_id,
            "target_date": target_date.isoformat(),
            "first_candle_start": signal.first.start.isoformat(timespec="seconds"),
            "first_candle_color": signal.first.color,
            "second_candle_start": signal.second.start.isoformat(timespec="seconds") if signal.second else None,
            "second_candle_color": signal.second.color if signal.second else None,
            "first_candle_volume": signal.first.volume,
            "first_candle_turnover": signal.first.turnover,
            "opening_volume_average": average,
            "opening_volume_samples": samples,
            "volume_multiplier": signal.volume_multiplier,
            "opening_colors_match": signal.colors_match,
            **qualification,
            "daily_filter": daily_filter,
            "first_candle_open": signal.first.open,
            "first_candle_high": signal.first.high,
            "is_fno": instrument.symbol in FNO_SYMBOLS,
            "status": "candidate" if qualification["possible_candidate"] else "Retest Break confirmed" if pattern["retest_break"] else "checked",
            "error": None,
        }

    @staticmethod
    def _backtest_error_row(
        instrument: Instrument,
        target_date: date,
        error: str,
    ) -> dict[str, Any]:
        return {
            "symbol": instrument.symbol,
            "name": instrument.name,
            "security_id": instrument.security_id,
            "target_date": target_date.isoformat(),
            "first_candle_start": None,
            "first_candle_color": None,
            "second_candle_start": None,
            "second_candle_color": None,
            "first_candle_volume": None,
            "opening_volume_average": None,
            "opening_volume_samples": [],
            "volume_multiplier": None,
            "opening_colors_match": False,
            "possible_candidate": False,
            "candidate_reason": None,
            "is_fno": instrument.symbol in FNO_SYMBOLS,
            "status": "error",
            "error": error,
        }

    @contextmanager
    def _priority_history(self):
        previous = getattr(self._request_context, "priority", False)
        with self._history_condition:
            self._priority_workers += 1
            self._request_context.priority = True
            self._history_condition.notify_all()
        try:
            yield
        finally:
            with self._history_condition:
                self._request_context.priority = previous
                self._priority_workers -= 1
                self._history_condition.notify_all()

    def evaluate_opening_candidates(self, client: Any | None = None, *, only_pending: bool = False) -> int:
        with self._priority_history():
            return self._confirm_opening_candidates(client, only_pending=only_pending)

    def _confirm_opening_candidates(self, client: Any | None = None, *, only_pending: bool = False) -> int:
        client = client or self._client()
        session = datetime.now(IST).date()
        if only_pending:
            self._screen_live_opening(session)
        with self._lock:
            states = sorted(self._states.values(), key=lambda state: state.provisional_setup is None)
        checked_count = 0
        first_error = None
        stop_event = getattr(self._request_context, "stop_event", None) or self._candidate_stop
        for index, state in enumerate(states):
            if only_pending and stop_event.is_set():
                break
            if only_pending and self._opening_check_complete(state, session):
                continue
            candles = []
            try:
                confirmed = state.confirmed_opening_candle
                candles = ([confirmed] if only_pending and confirmed and confirmed.start.date() == session
                           else self._fetch_opening_candles(client, state.instrument))
                # Publish Redwala immediately, independent of historical filter availability.
                with self._lock:
                    if (only_pending and stop_event.is_set()) or self._states.get(state.instrument.symbol) is not state:
                        break
                    self._apply_opening_candidate(state.instrument.symbol, candles)
                self._prepare_daily(client, state, session)
                if only_pending and stop_event.is_set():
                    break
                if state.daily_filter["passes"] and (not state.opening_volume_average or (state.volume_session and state.volume_session != session)):
                    self._prepare_volume(client, state, session, stop_event if only_pending else None)
                    if only_pending and stop_event.is_set():
                        break
                    self.store.update_opening_volume_cache({state.instrument.symbol: self._cache_entry(state)})
                with self._lock:
                    if (only_pending and stop_event.is_set()) or self._states.get(state.instrument.symbol) is not state:
                        break
                    self._apply_opening_candidate(state.instrument.symbol, candles)
                    state.opening_metadata_pending = False
                checked_count += 1
            except Exception as exc:
                if state.redwala_gira and candles:
                    state.opening_metadata_pending = True
                    # Missing daily/minute history affects other setups and PDL metadata only.
                    state.candidate_reason += f"; other setup history unavailable: {exc}"
                    checked_count += 1
                    if not _should_stop_api_batch(exc):
                        continue
                first_error = first_error or str(exc)
                with self._lock:
                    state.possible_candidate = state.retest_break = False
                    state.qualifies_scan = state.redwala_gira
                    if not state.redwala_gira:
                        state.signal_session = None
                        state.confirmation_status = "unresolved"
                    state.error = str(exc)
                    state.candidate_reason = f"Opening candle check failed: {exc}"
                if _should_stop_api_batch(exc):
                    for remaining in states[index + 1:]:
                        if not self._opening_check_complete(remaining, session):
                            remaining.error = f"Opening candle check skipped: {exc}"
                            remaining.confirmation_status = "unresolved"
                    raise RuntimeError(str(exc)) from exc
        if states and checked_count == 0 and first_error:
            raise RuntimeError(first_error)
        # Circuit quotes have their own worker and never delay automatic confirmation.
        if not only_pending:
            self.refresh_circuit_limits(client)
        with self._lock:
            return sum(state.possible_candidate for state in self._states.values())

    def _screen_live_opening(self, session: date, states: list[StockState] | None = None) -> None:
        now = datetime.now(IST)
        if now < datetime.combine(session, dt_time(9, 16), tzinfo=IST):
            return
        with self._lock:
            for state in states if states is not None else self._states.values():
                if self._opening_check_complete(state, session):
                    continue
                # Close by the clock, even when the next trade has not arrived.
                current = state.current_candle
                if current and current.start.date() == session and current.start.time() == dt_time(9, 15) and current.end <= now:
                    self._merge_opening_candles(state, [Candle(current.start, current.open, current.high, current.low, current.close, current.volume)])
                first = self._first_opening_candle(state.opening_candles)
                if not first or first.start.date() != session:
                    continue
                signal = self._calculate_opening_signal([first], state.opening_volume_average if self._volume_ready(state, session) else None)
                result = self._qualify_signal(signal, state.daily_filter, session)
                state.today_opening_volume = first.volume
                state.volume_multiplier = signal.volume_multiplier
                state.provisional_setup = ("Possible candidate" if result["possible_candidate"] else
                                           "redwala gira" if result["redwala_gira"] else None)
                if state.provisional_setup:
                    state.confirmation_status = "awaiting_confirmation"
                    state.status = "Awaiting confirmation"
                    state.candidate_reason = "Live-derived match; awaiting Dhan's completed first candle"
                elif ((first.color != "red" or first.open != first.high) and self._volume_ready(state, session)
                      and self._live_opening_complete(state, session)
                      and state.opening_boundary_volume - state.feed_baseline_volume
                      < self.volume_filters.minute_volume_min * state.opening_volume_average):
                    state.confirmation_status = "local_rejected"
                    state.signal_session = session
                    state.status = "First-candle live filter failed"
                    state.candidate_reason = result["candidate_reason"]
                # An incomplete observation must go to historical confirmation, including apparent rejects.

    def _live_opening_complete(self, state: StockState, session: date) -> bool:
        opening = datetime.combine(session, dt_time(9, 15), tzinfo=IST)
        return bool(self._connected and not state.feed_incomplete and state.feed_baseline_session == session
                    and state.feed_baseline_volume is not None and state.opening_boundary_volume is not None
                    and state.opening_boundary_volume >= state.feed_baseline_volume
                    and state.opening_boundary_seen and state.opening_first_tick
                    and opening <= state.opening_first_tick <= opening + timedelta(seconds=2)
                    and state.opening_last_tick and state.opening_last_tick >= opening + timedelta(seconds=58))

    def refresh_circuit_limits(self, client: Any | None = None) -> None:
        # Quote failures must not alter the independent opening-setup qualification.
        if not self._circuit_refresh_lock.acquire(blocking=False):
            return
        try:
            now = datetime.now(IST)
            with self._lock:
                states = [state for state in self._states.values()
                          if state.qualifies_scan and state.signal_session == now.date()
                          and (state.circuit_attempt_at is None
                               or state.circuit_attempt_at.date() != now.date()
                               or (now - state.circuit_attempt_at).total_seconds() >= CIRCUIT_REFRESH_SECONDS)]
                for state in states:
                    state.circuit_attempt_at = now
            if not states:
                return
            try:
                client = client or self._client()
                for offset in range(0, len(states), 1000):
                    batch = states[offset:offset + 1000]
                    securities: dict[str, list[int]] = {}
                    for state in batch:
                        securities.setdefault(state.instrument.exchange_segment, []).append(int(state.instrument.security_id))
                    requested_at = datetime.now(IST)
                    response = self._quote_call(client.quote_data, securities)
                    # The SDK wraps the quote endpoint's own status/data envelope.
                    data = _extract_data(_extract_data(response))
                    fetched_at = datetime.now(IST)
                    with self._lock:
                        for state in batch:
                            if self._states.get(state.instrument.symbol) is not state:
                                continue
                            segment = data.get(state.instrument.exchange_segment) or {}
                            item = segment.get(state.instrument.security_id) or segment.get(int(state.instrument.security_id)) or {}
                            upper = _float_or_none(item.get("upper_circuit_limit"))
                            lower = _float_or_none(item.get("lower_circuit_limit"))
                            upper = upper if upper is not None and upper > 0 else None
                            lower = lower if lower is not None and lower > 0 else None
                            if upper is not None and lower is not None and lower > upper:
                                upper = lower = None
                            state.upper_circuit_limit = upper
                            state.lower_circuit_limit = lower
                            state.circuit_fetched_at = fetched_at
                            state.circuit_error = None if upper is not None and lower is not None else "Dhan circuit limit unavailable or invalid"
                            price = _float_or_none(item.get("last_price"))
                            # Do not replace a WebSocket tick received while the quote was in flight.
                            if price is not None and price > 0 and (state.last_tick_received_at is None or state.last_tick_received_at < requested_at):
                                state.ltp = price
                                if state.previous_close:
                                    state.percent_change = (price - state.previous_close) / state.previous_close * 100
            except Exception as exc:
                with self._lock:
                    for state in states:
                        if self._states.get(state.instrument.symbol) is state:
                            state.upper_circuit_limit = state.lower_circuit_limit = None
                            state.circuit_error = f"Circuit quote failed: {exc}"
        finally:
            self._circuit_refresh_lock.release()

    def _quote_call(self, method: Any, securities: dict[str, list[int]]) -> Any:
        # OHLC and full quotes share Dhan's one-request-per-second quote allowance.
        with self._quote_lock:
            delay = 1.05 - (time.monotonic() - self._last_quote_call)
            if delay > 0:
                time.sleep(delay)
            self._last_quote_call = time.monotonic()
            return method(securities)

    def _refresh_circuit_limits_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            self.refresh_circuit_limits()
            if stop_event.wait(CIRCUIT_REFRESH_SECONDS):
                return

    def _apply_opening_candidate(self, symbol: str, candles: list[Candle]) -> bool:
        with self._lock:
            target = self._states.get(symbol)
            if target is None:
                return False
            self._merge_opening_candles(target, candles)
            first = self._first_opening_candle(candles)
            average = (target.opening_volume_average if first and (target.volume_session is None or target.volume_session == first.start.date()) else None)
        signal = self._calculate_opening_signal(candles, average)
        with self._lock:
            target = self._states.get(symbol)
            if target is None:
                return False
            target.today_opening_volume = signal.first.volume
            target.confirmed_opening_candle = signal.first
            self._merge_confirmed_session(target, candles)
            target.daily_filter = apply_daily_volume_limit(target.daily_filter, self.volume_filters.daily_volume_max)
            target.volume_multiplier = signal.volume_multiplier
            target.opening_colors_match = signal.colors_match
            qualification = self._qualify_signal(signal, target.daily_filter, signal.first.start.date())
            target.signal_session = signal.first.start.date()
            target.opening_pair_confirmed = signal.second is not None
            target.possible_candidate = qualification["possible_candidate"]
            target.redwala_gira = qualification["redwala_gira"]
            target.qualifies_scan = qualification["qualifies_scan"]
            target.candidate_reason = qualification["candidate_reason"]
            target.confirmation_status = "confirmed"
            missing = (missing_opening_history(target.daily_filter, signal.first.start.date(), self.volume_filters)
                       if signal.first.color == "green" else None)
            if (self.volume_filters.today_open_cross and signal.first.color == "green"
                    and self._five_day_close_level(target.daily_filter, signal.first.start.date()) is None):
                missing = missing or "Today Open Cross needs five completed trading-session closes"
            if missing:
                target.confirmation_status = "unresolved"
            target.provisional_setup = None
            target.error = (missing + "; cache day levels or run Live to fetch them" if missing else None)
            self._update_retest(target)
            return target.possible_candidate

    def _retest_result(self, first: Candle, candles: list[Candle], daily: dict | None, qualification: dict) -> dict:
        if not qualification["retest_base_eligible"]:
            return {"retest_break": False, "retest_break_at": None, "retest_status": "filtered",
                    "retest_reason": "Requires a red first candle and the configured daily-volume, opening-volume and turnover filters"}
        if not qualification["retest_eligible"]:
            checks = evaluate_opening_filters(daily, first.start.date(), first.open, self.volume_filters)
            if not checks["passes"]:
                return {"retest_break": False, "retest_break_at": None,
                        "retest_status": "filtered" if checks["resolved"] else "unresolved",
                        "retest_reason": "Retest Break: " + checks["reason"]}
            missing = self.volume_filters.today_open_cross and self._five_day_close_level(daily, first.start.date()) is None
            return {"retest_break": False, "retest_break_at": None,
                    "retest_status": "unresolved" if missing else "filtered",
                    "retest_reason": "Retest Break: five-session closes unavailable" if missing else "Retest Break: Today Open Cross failed"}
        return retest_sequence(first, candles)

    @staticmethod
    def _merge_confirmed_session(state: StockState, candles: list[Candle]) -> None:
        if not candles:
            return
        session = max(bar.start.date() for bar in candles)
        state.confirmed_session_candles = {start: bar for start, bar in state.confirmed_session_candles.items()
                                           if start.date() == session}
        state.confirmed_session_candles.update({bar.start: bar for bar in candles if bar.start.date() == session})

    def _update_retest(self, state: StockState) -> None:
        first = state.confirmed_opening_candle
        if not first:
            return
        average = (state.opening_volume_average if state.volume_session is None
                   or state.volume_session == first.start.date() else None)
        signal = self._calculate_opening_signal([first], average)
        qualification = self._qualify_signal(signal, state.daily_filter, first.start.date())
        result = self._retest_result(first, list(state.confirmed_session_candles.values()), state.daily_filter, qualification)
        state.retest_break = result["retest_break"]
        state.retest_break_at = result["retest_break_at"]
        state.retest_status = result["retest_status"]
        state.retest_reason = result["retest_reason"]
        state.qualifies_scan = state.possible_candidate or state.redwala_gira or state.retest_break
        if state.retest_break:
            state.status = "Retest Break confirmed"

    def evaluate_retest_breaks(self, stop_event: threading.Event | None = None) -> int:
        """Confirm only volume-qualified red stocks, once each new minute is ready."""
        now = datetime.now(IST)
        cutoff = min(now.replace(second=0, microsecond=0),
                     datetime.combine(now.date(), dt_time(15, 30), tzinfo=IST))
        client = None
        with self._lock:
            states = list(self._states.values())
        for state in states:
            if stop_event and stop_event.is_set():
                break
            with self._lock:
                first = state.confirmed_opening_candle
                if (not first or first.start.date() != now.date() or first.end >= cutoff
                        or not state.opening_volume_average):
                    continue
                signal = self._calculate_opening_signal([first], state.opening_volume_average)
                qualification = self._qualify_signal(signal, state.daily_filter, now.date())
                if not qualification["retest_base_eligible"] or state.retest_status in {"confirmed", "rejected"}:
                    continue
                needs_daily = bool(missing_opening_history(state.daily_filter, now.date(), self.volume_filters)
                                   or (self.volume_filters.today_open_cross and self._five_day_close_level(state.daily_filter, now.date()) is None))
                if not qualification["retest_eligible"] and not needs_daily:
                    continue
                if state.retest_attempt_at and (now - state.retest_attempt_at).total_seconds() < 5:
                    continue
                if state.retest_checked_through and state.retest_checked_through >= cutoff and state.retest_status != "unresolved":
                    continue
                state.retest_attempt_at = now
            try:
                client = client or self._client()
                if needs_daily:
                    daily = self._fetch_daily_filter(client, state.instrument, now.date())
                    with self._lock:
                        if (stop_event and stop_event.is_set()) or self._states.get(state.instrument.symbol) is not state:
                            continue
                        state.daily_filter = apply_daily_volume_limit(daily, self.volume_filters.daily_volume_max)
                        self._update_retest(state)
                        qualification = self._qualify_signal(signal, state.daily_filter, now.date())
                    self.store.update_opening_volume_cache({state.instrument.symbol: self._cache_entry(state)})
                    if not qualification["retest_eligible"]:
                        continue
                response = self._intraday_with_retry(
                    client, state.instrument.security_id, state.instrument.exchange_segment,
                    state.instrument.instrument_type, first.start.strftime("%Y-%m-%d %H:%M:%S"),
                    cutoff.strftime("%Y-%m-%d %H:%M:%S"))
                candles = [bar for bar in self._parse_intraday_candles(response)
                           if bar.start.date() == now.date() and first.start <= bar.start and bar.end <= cutoff]
                with self._lock:
                    if (stop_event and stop_event.is_set()) or self._states.get(state.instrument.symbol) is not state:
                        continue
                    if self._first_opening_candle(candles):
                        self._apply_opening_candidate(state.instrument.symbol, candles)
                    else:
                        self._merge_confirmed_session(state, candles)
                        self._update_retest(state)
                    if candles:
                        state.retest_checked_through = max(bar.end for bar in candles)
                    if state.retest_status == "waiting" and (not candles or state.retest_checked_through < cutoff):
                        state.retest_status = "unresolved"
                        state.retest_reason = "Waiting for Dhan's latest completed minute candle"
            except Exception as exc:
                with self._lock:
                    if not stop_event or not stop_event.is_set():
                        state.retest_status = "unresolved"
                        state.retest_reason = f"Retest confirmation unavailable: {exc}"
                if _should_stop_api_batch(exc):
                    raise
        with self._lock:
            return sum(state.retest_break for state in self._states.values())

    def _refresh_retest_breaks(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(1):
            now = datetime.now(IST)
            if not dt_time(9, 17) <= now.time() <= dt_time(15, 31):
                continue
            try:
                self.evaluate_retest_breaks(stop_event)
            except Exception as exc:
                LOGGER.warning("Retest confirmation failed: %s", exc)
                if stop_event.wait(30):
                    return

    def _calculate_opening_signal(
        self,
        candles: list[Candle],
        volume_average: float | None,
    ) -> OpeningSignal:
        if volume_average is not None and volume_average <= 0:
            raise ValueError("Opening volume average must be greater than zero")
        colors_match, color_reason = self._evaluate_first_opening_candle(candles)
        first = self._first_opening_candle(candles)
        if first is None:
            raise RuntimeError("Dhan did not return the first opening candle")
        first_label = first.start.strftime("%H:%M")
        second_label = first.end.strftime("%H:%M")
        second = next((candle for candle in candles if candle.start == first.end), None)
        multiplier = first.volume / volume_average if volume_average else None
        possible_candidate = colors_match and multiplier is not None and multiplier >= self.volume_filters.minute_volume_min
        reason = (
            f"{color_reason}; opening volume {first.volume:,} / average {volume_average:,.0f} "
            f"= {multiplier:.2f}x (minimum {self.volume_filters.minute_volume_min:g}x)"
        ) if volume_average else f"{color_reason}; opening-volume history unavailable"
        return OpeningSignal(
            first_label=first_label,
            first=first,
            second_label=second_label,
            second=second,
            volume_average=volume_average,
            volume_multiplier=multiplier,
            colors_match=colors_match,
            possible_candidate=possible_candidate,
            reason=reason,
        )

    def _fetch_opening_candles(self, client: Any, instrument: Instrument) -> list[Candle]:
        now = datetime.now(IST)
        today = now.date()
        session_start = datetime.combine(today, dt_time(9, 14), tzinfo=IST)
        session_end = min(now, datetime.combine(today, dt_time(9, 20), tzinfo=IST))
        response = self._intraday_with_retry(
            client,
            instrument.security_id,
            instrument.exchange_segment,
            instrument.instrument_type,
            session_start.strftime("%Y-%m-%d %H:%M:%S"),
            session_end.strftime("%Y-%m-%d %H:%M:%S"),
        )
        return [
            candle for candle in self._parse_intraday_candles(response)
            if candle.start.date() == today and candle.end <= now
        ]

    def _evaluate_first_opening_candle(self, candles: list[Candle]) -> tuple[bool, str]:
        # Retain the legacy field name for API compatibility; only the first colour matters.
        first = self._first_opening_candle(candles)
        if first is None:
            raise RuntimeError("Dhan did not return the first opening candle")
        return first.color == "green", f"First candle {first.start:%H:%M} {first.color}; second candle not required"

    @staticmethod
    def _opening_window_candles(candles: list[Candle]) -> list[Candle]:
        if not candles:
            return []
        session_date = max(candle.start.date() for candle in candles)
        by_start = {
            candle.start: candle
            for candle in candles
            if candle.start.date() == session_date
            and dt_time(9, 14) <= candle.start.time() <= dt_time(9, 19)
        }
        ordered = sorted(by_start.values(), key=lambda candle: candle.start)
        if not ordered:
            return []
        first_start = next(
            (
                candle.start
                for candle in ordered
                if candle.start.time() == dt_time(9, 14)
            ),
            datetime.combine(session_date, dt_time(9, 15), tzinfo=IST),
        )
        last_start = first_start + timedelta(minutes=4)
        return [
            candle for candle in ordered if first_start <= candle.start <= last_start
        ]

    def _merge_opening_candles(self, state: StockState, candles: list[Candle]) -> None:
        if not candles:
            return
        latest_date = max(candle.start.date() for candle in candles)
        existing = {
            candle.start: candle
            for candle in state.opening_candles
            if candle.start.date() == latest_date
        }
        for candle in candles:
            if candle.start.date() == latest_date:
                existing[candle.start] = candle
        state.opening_candles = self._opening_window_candles(list(existing.values()))

    def _parse_intraday_candles(self, response: Any) -> list[Candle]:
        data = _extract_data(response)
        timestamps = data.get("timestamp") or []
        opens = data.get("open") or []
        highs = data.get("high") or []
        lows = data.get("low") or []
        closes = data.get("close") or []
        volumes = data.get("volume") or []
        if any(len(values) != len(timestamps) for values in (opens, highs, lows, closes, volumes)):
            raise ValueError("Dhan intraday history has mismatched candle arrays")
        candles: list[Candle] = []
        for index, ts in enumerate(timestamps):
            try:
                candle_start = datetime.fromtimestamp(int(float(ts)), IST).replace(second=0, microsecond=0)
                volume = float(volumes[index])
                if not math.isfinite(volume) or volume < 0 or not volume.is_integer():
                    raise ValueError("Invalid candle volume")
                candle = Candle(
                        start=candle_start,
                        open=float(opens[index]),
                        high=float(highs[index]),
                        low=float(lows[index]),
                        close=float(closes[index]),
                        volume=int(volume),
                    )
                prices = (candle.open, candle.high, candle.low, candle.close)
                if (not all(math.isfinite(price) and price > 0 for price in prices)
                        or candle.low > min(candle.open, candle.close)
                        or candle.high < max(candle.open, candle.close)):
                    raise ValueError("Invalid candle OHLC prices")
                candles.append(candle)
            except (IndexError, TypeError, ValueError, OverflowError, OSError) as exc:
                raise ValueError(f"Invalid Dhan intraday candle at index {index}: {exc}") from exc
        return candles

    def _cache_from_ohlc_batch(self, client: Any, states: list[StockState]) -> dict[str, float]:
        if not states:
            return {}
        security_ids = [int(state.instrument.security_id) for state in states]
        response = self._ohlc_batch_with_retry(client, {"NSE_EQ": security_ids})
        data = _extract_data(response)
        segment_data = data.get("NSE_EQ", {})
        cached: dict[str, float] = {}
        for state in states:
            symbol = state.instrument.symbol
            item = segment_data.get(state.instrument.security_id) or segment_data.get(int(state.instrument.security_id))
            if not isinstance(item, dict):
                continue
            close = _float_or_none((item.get("ohlc") or {}).get("close"))
            if close is None:
                continue
            cached[symbol] = close
            ltp = _float_or_none(item.get("last_price"))
            with self._lock:
                target = self._states.get(symbol)
                if not target:
                    continue
                target.previous_close = close
                target.ltp = ltp if ltp is not None else target.ltp
                if target.ltp is not None and close:
                    target.percent_change = ((target.ltp - close) / close) * 100
                target.error = None
                target.status = "cached"
        return cached

    def _ohlc_batch_with_retry(self, client: Any, securities: dict[str, list[int]]) -> Any:
        last_error: str | None = None
        for attempt in range(3):
            response = self._quote_call(client.ohlc_data, securities)
            if isinstance(response, dict) and response.get("status") == "failure":
                last_error = _format_dhan_error(response.get("remarks"))
                if "DH-904" in last_error or "Rate_Limit" in last_error:
                    if attempt < 2:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    raise RuntimeError(last_error)
            return response
        raise RuntimeError(last_error or "Dhan OHLC batch request failed")

    def _historical_daily_with_retry(self, client: Any, *args: Any) -> Any:
        last_error: str | None = None
        for attempt in range(3):
            try:
                response = self._history_call(client.historical_daily_data, *args)
                if isinstance(response, dict) and response.get("status") == "failure":
                    last_error = _format_dhan_error(response.get("remarks"))
                    if "DH-904" in last_error or "Rate_Limit" in last_error:
                        if attempt < 2:
                            time.sleep(1.25 * (attempt + 1))
                            continue
                    return response
                return response
            except Exception as exc:
                last_error = str(exc)
            if attempt < 2:
                time.sleep(1.25 * (attempt + 1))
        if last_error:
            raise RuntimeError(last_error)
        return client.historical_daily_data(*args)

    def _intraday_with_retry(self, client: Any, *args: Any) -> Any:
        last_error: str | None = None
        for attempt in range(3):
            response = self._history_call(client.intraday_minute_data, *args, interval=1, oi=False)
            if isinstance(response, dict) and response.get("status") == "failure":
                last_error = _format_dhan_error(response.get("remarks"))
                if "DH-904" in last_error or "Rate_Limit" in last_error:
                    if attempt < 2:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    raise RuntimeError(last_error)
            return response
        raise RuntimeError(last_error or "Dhan intraday request failed")

    def _history_call(self, method: Any, *args: Any, **kwargs: Any) -> Any:
        priority = getattr(self._request_context, "priority", False)
        while True:
            with self._history_condition:
                while not priority and self._history_reserved():
                    self._history_condition.wait(0.1)
            with self._history_lock:
                # Recheck after a request already in flight finishes.
                if not priority and self._history_reserved():
                    continue
                delay = HISTORY_REQUEST_SPACING - (time.monotonic() - self._last_history_call)
                if delay > 0:
                    time.sleep(delay)
                self._last_history_call = time.monotonic()
                return method(*args, **kwargs)

    def _history_reserved(self) -> bool:
        now = datetime.now(IST)
        opening_due = self._running and not self._opening_finished and dt_time(9, 16) <= now.time() < dt_time(9, 30)
        return self._priority_workers > 0 or opening_due






    def start(self) -> None:
        if MarketFeed is None or DhanContext is None:
            raise RuntimeError("dhanhq SDK is not installed. Run: py -m pip install -r requirements.txt")
        config = self.store.load()
        if not config.client_id or not config.access_token:
            raise RuntimeError("Save Dhan client ID and access token first")
        with self._lock:
            if not self._states:
                raise RuntimeError("Add stocks first")
        self.stop()

        with self._lock:
            session = datetime.now(IST).date()
            states = list(self._states.values())
            if not states:
                raise RuntimeError("All stocks fail today's previous-day filter")
            self._opening_finished = False
            self._subscribed_symbols = {state.instrument.symbol for state in states}
            for state in states:
                state.feed_incomplete = True
                state.feed_baseline_session = None
                state.feed_baseline_volume = None
                state.opening_boundary_volume = None
                state.opening_boundary_seen = False
                state.opening_first_tick = state.opening_last_tick = None
                state.last_cumulative_volume = None
                state.current_candle = None
                if state.signal_session != session:
                    state.confirmation_status = "pending"
                    state.provisional_setup = None
                    state.possible_candidate = state.redwala_gira = state.retest_break = state.qualifies_scan = False
                    state.opening_candles = []
                    state.confirmed_session_candles = {}
                    state.retest_break = False
                    state.retest_status = "waiting"
                    state.retest_break_at = None
                    state.retest_reason = None
                    state.retest_checked_through = None
                    state.retest_attempt_at = None
            self._running = True
            self._connected = False
            self._status = "Connecting to Dhan websocket..."

        instruments = [
            (MarketFeed.NSE, state.instrument.security_id, MarketFeed.Quote)
            for state in states
        ]
        try:
            context = DhanContext(config.client_id, config.access_token)
            self._feed = MarketFeed(
                context,
                instruments,
                "v2",
                on_connect=self._on_connect,
                on_message=self._on_message,
                on_close=self._on_close,
                on_error=self._on_error,
            )
            self._feed_thread = self._feed.start()
            self._candidate_stop = threading.Event()
            self._candidate_refresh = threading.Event()
            self._subscription_refresh = threading.Event()
            self._candidate_thread = threading.Thread(
                target=self._refresh_opening_candidates_when_ready,
                args=(self._candidate_stop, self._candidate_refresh),
                name="opening-candidate-refresh",
                daemon=True,
            )
            self._candidate_thread.start()
            threading.Thread(target=self._refresh_retest_breaks, args=(self._candidate_stop,),
                             name="retest-break-refresh", daemon=True).start()
            threading.Thread(target=self._refresh_filter_subscriptions,
                             args=(self._feed, self._candidate_stop, self._subscription_refresh),
                             name="filter-subscription-refresh", daemon=True).start()
            self._circuit_thread = threading.Thread(
                target=self._refresh_circuit_limits_loop,
                args=(self._candidate_stop,),
                name="circuit-limit-refresh",
                daemon=True,
            )
            self._circuit_thread.start()
        except Exception as exc:
            self.stop()
            with self._lock:
                self._status = f"Live start failed: {exc}"
            raise

    def stop(self) -> None:
        feed = self._feed
        self._candidate_stop.set()
        self._opening_finished = True
        with self._history_condition:
            self._history_condition.notify_all()
        with self._lock:
            self._running = False
            self._connected = False
            self._feed = None
            self._feed_thread = None
            self._candidate_thread = None
            self._circuit_thread = None
            if self._status != "Idle":
                self._status = "Stopped"
        if feed is not None:
            try:
                feed.close_connection()
            except Exception as exc:
                LOGGER.warning("Error closing Dhan feed: %s", exc)

    def _opening_check_complete(self, state: StockState, session: date) -> bool:
        if state.opening_metadata_pending:
            return False
        if (state.signal_session == session and state.confirmation_status == "confirmed"
                and state.redwala_gira):
            return True
        daily = state.daily_filter
        return bool(state.signal_session == session and daily and self._daily_ready(state, session)
                    and daily.get("session_date") == session.isoformat()
                    and "previous_high" in daily and "previous_low" in daily
                    and state.confirmation_status in {"confirmed", "local_rejected"})

    def _refresh_opening_candidates_when_ready(self, stop_event: threading.Event,
                                              refresh_event: threading.Event) -> None:
        self._request_context.stop_event = stop_event
        try:
            while not stop_event.is_set():
                refresh_event.clear()
                if stop_event is self._candidate_stop:
                    self._opening_finished = False
                self._run_opening_confirmation(stop_event)
                if stop_event is self._candidate_stop:
                    self._opening_finished = True
                with self._history_condition:
                    self._history_condition.notify_all()
                # Keep the worker available after the initial opening scan so a
                # lower threshold can reopen rejected stocks without restarting Live.
                while not stop_event.is_set() and not refresh_event.wait(0.25):
                    pass
        finally:
            if stop_event is self._candidate_stop:
                self._opening_finished = True
            with self._history_condition:
                self._history_condition.notify_all()
            self._request_context.stop_event = None

    def _run_opening_confirmation(self, stop_event: threading.Event) -> None:
        now = datetime.now(IST)
        ready_at = datetime.combine(now.date(), dt_time(9, 16), tzinfo=IST)
        if stop_event.wait(max((ready_at - now).total_seconds(), 0)):
            return
        self._screen_live_opening(now.date())
        for attempt in range(6):
            if attempt and stop_event.wait(2):
                return
            with self._lock:
                if self._states and all(self._opening_check_complete(state, now.date()) for state in self._states.values()):
                    return
            try:
                count = self.evaluate_opening_candidates(only_pending=True)
                with self._lock:
                    if self._running:
                        unresolved = sum(not self._opening_check_complete(state, now.date()) for state in self._states.values())
                        self._status = f"Opening scan: {count} confirmed possible candidate(s); {unresolved} unresolved"
            except Exception as exc:
                LOGGER.warning("Automatic opening candidate refresh failed: %s", exc)
                if _should_stop_api_batch(exc):
                    return

    def repair_missing_candles(self) -> int:
        client = self._client()
        repaired = 0
        with self._lock:
            states = list(self._states.values())

        now_floor = datetime.now(IST).replace(second=0, microsecond=0)
        latest_finished = now_floor - timedelta(minutes=1)
        for state in states:
            start = None
            with self._lock:
                if state.completed_candle:
                    start = state.completed_candle.start + timedelta(minutes=1)
                elif state.current_candle:
                    start = state.current_candle.start
            if start is None or start > latest_finished:
                continue
            try:
                repaired += self._repair_symbol(client, state.instrument, start, latest_finished)
            except Exception as exc:
                with self._lock:
                    if state.instrument.symbol in self._states:
                        self._states[state.instrument.symbol].error = f"Repair failed: {exc}"
        with self._lock:
            self._status = f"Repaired {repaired} candle(s)" if repaired else "No missing candles found"
        return repaired

    def _repair_symbol(self, client: Any, instrument: Instrument, start: datetime, end: datetime) -> int:
        response = self._intraday_with_retry(
            client,
            instrument.security_id,
            instrument.exchange_segment,
            instrument.instrument_type,
            start.strftime("%Y-%m-%d %H:%M:%S"),
            (end + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        data = _extract_data(response)
        repaired = 0
        for candle in self._parse_intraday_candles(data):
            candle_start = candle.start
            if candle_start < start or candle_start > end:
                continue
            with self._lock:
                state = self._states.get(instrument.symbol)
                if state and (state.completed_candle is None or candle.start >= state.completed_candle.start):
                    state.completed_candle = candle
                    self._merge_opening_candles(state, [candle])
                    self._merge_confirmed_session(state, [candle])
                    self._update_retest(state)
                    state.status = "repaired"
                    repaired += 1
        return repaired

    def _on_connect(self, _feed: Any) -> None:
        if _feed is not None and _feed is not self._feed:
            return
        with self._lock:
            self._connected = True
            self._status = "Live feed connected"
            for state in self._states.values():
                state.status = "live"

    def _on_close(self, _feed: Any) -> None:
        if _feed is not None and _feed is not self._feed:
            return
        with self._lock:
            self._connected = False
            self._invalidate_opening_feed()
            if self._running:
                self._status = "Live feed disconnected"

    def _on_error(self, _feed: Any, error: Exception) -> None:
        if _feed is not None and _feed is not self._feed:
            return
        with self._lock:
            self._connected = False
            self._status = f"Feed error: {error}"
            self._invalidate_opening_feed()

    def _invalidate_opening_feed(self) -> None:
        for state in self._states.values():
            state.feed_incomplete = True
            if state.confirmation_status == "local_rejected":
                state.confirmation_status = "pending"
                state.signal_session = None

    def _on_message(self, _feed: Any, data: Any) -> None:
        if _feed is not None and _feed is not self._feed:
            return
        if not isinstance(data, dict):
            return
        security_id = str(data.get("security_id", ""))
        with self._lock:
            symbol = self._security_symbols.get(security_id)
            if symbol not in self._states:
                symbol = next((key for key, state in self._states.items() if state.instrument.security_id == security_id), None)
                if symbol:
                    self._security_symbols[security_id] = symbol
        if not symbol:
            return

        if data.get("type") == "Previous Close":
            close = _float_or_none(data.get("prev_close"))
            if close is not None:
                with self._lock:
                    self._states[symbol].previous_close = close
                    self._states[symbol].status = "live"
                self.store.update_previous_closes({symbol: close})
            return

        ltp = _float_or_none(data.get("LTP"))
        if ltp is None:
            return
        cumulative_volume = _int_or_none(data.get("volume"))
        tick_time = self._tick_time(data.get("LTT"))
        candle_start = tick_time.replace(second=0, microsecond=0)

        with self._lock:
            state = self._states[symbol]
            state.ltp = ltp
            state.day_volume = cumulative_volume if cumulative_volume is not None else state.day_volume
            state.last_tick_time = tick_time
            state.last_tick_received_at = datetime.now(IST)
            if state.confirmation_status not in {"awaiting_confirmation", "unresolved", "local_rejected", "daily_rejected"}:
                state.status = "live"
            received_at = datetime.now(IST)
            opening = datetime.combine(received_at.date(), dt_time(9, 15), tzinfo=IST)
            if tick_time.date() == received_at.date() and opening + timedelta(minutes=1) <= tick_time < opening.replace(hour=15, minute=30):
                if state.post_opening_trough_session != tick_time.date():
                    state.post_opening_trough_session = tick_time.date()
                    state.post_opening_trough = ltp
                else:
                    state.post_opening_trough = min(state.post_opening_trough if state.post_opening_trough is not None else ltp, ltp)
                if state.post_opening_peak_session != tick_time.date():
                    state.post_opening_peak_session = tick_time.date()
                    state.post_opening_peak = ltp
                else:
                    state.post_opening_peak = max(state.post_opening_peak or ltp, ltp)
            if tick_time.date() != received_at.date() or cumulative_volume is None:
                state.feed_incomplete = True
            elif received_at < opening and tick_time < opening and self._connected:
                state.feed_baseline_session = received_at.date()
                state.feed_baseline_volume = cumulative_volume
                state.feed_incomplete = False
            elif opening <= tick_time < opening + timedelta(minutes=1):
                if state.opening_first_tick is None:
                    state.opening_first_tick = tick_time
                state.opening_last_tick = tick_time
                if received_at - tick_time > timedelta(seconds=3):
                    state.feed_incomplete = True
                if state.confirmation_status == "local_rejected":
                    state.confirmation_status = "pending"
                    state.signal_session = None
            elif tick_time >= opening + timedelta(minutes=1) and state.opening_boundary_volume is None:
                state.opening_boundary_seen = True
                state.opening_boundary_volume = cumulative_volume
            if cumulative_volume is not None and state.last_cumulative_volume is not None and cumulative_volume < state.last_cumulative_volume:
                state.feed_incomplete = True
            if state.previous_close:
                state.percent_change = ((ltp - state.previous_close) / state.previous_close) * 100

            volume_delta = 0
            if cumulative_volume is not None:
                if state.last_cumulative_volume is not None and cumulative_volume >= state.last_cumulative_volume:
                    volume_delta = cumulative_volume - state.last_cumulative_volume
                state.last_cumulative_volume = cumulative_volume

            if tick_time < opening:
                # Premarket quotes seed volume, not a fake 09:14 opening candle.
                return

            if state.current_candle is None:
                state.current_candle = Candle(candle_start, ltp, ltp, ltp, ltp, volume_delta)
                return

            if candle_start == state.current_candle.start:
                state.current_candle.update(ltp, volume_delta)
                return

            if candle_start > state.current_candle.start:
                state.completed_candle = state.current_candle
                existing_first = self._first_opening_candle(state.opening_candles)
                if not (state.confirmation_status == "confirmed" and existing_first
                        and existing_first.start == state.completed_candle.start):
                    self._merge_opening_candles(state, [state.completed_candle])
                state.current_candle = Candle(candle_start, ltp, ltp, ltp, ltp, volume_delta)
                return

            state.feed_incomplete = True

    def _tick_time(self, ltt: Any) -> datetime:
        if isinstance(ltt, str) and ltt:
            try:
                parsed_time = dt_time.fromisoformat(ltt)
                now_ist = datetime.now(IST)
                candidate = datetime.combine(now_ist.date(), parsed_time, tzinfo=IST)
                if candidate - now_ist > timedelta(hours=12):
                    candidate -= timedelta(days=1)
                elif now_ist - candidate > timedelta(hours=12):
                    candidate += timedelta(days=1)
                return candidate
            except ValueError:
                pass
        return datetime.now(IST)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            rows = [self._row(state) for state in self._states.values()]
            rows.sort(
                key=lambda row: (
                    row["possible_candidate"],
                    row["percent_change"] if row["percent_change"] is not None else -999999,
                    row["candle_turnover"],
                ),
                reverse=True,
            )
            return {
                "running": self._running,
                "volume_filters": self._volume_filters.model_dump(),
                "connected": self._connected,
                "status": self._status,
                "stocks": rows,
                "unresolved_symbols": list(self._unresolved_symbols),
                "updated_at": datetime.now(IST).isoformat(timespec="seconds"),
            }

    @staticmethod
    def _redwala_breaks(first: Candle | None, candles: list[Candle], daily: dict | None,
                        eligible: bool, trough: float | None = None) -> dict:
        result = {"first_candle_low_break": False, "previous_day_low_break": False}
        if not eligible or not first:
            return result
        lows = [bar.low for bar in candles if bar.start.date() == first.start.date()
                and first.end <= bar.start and bar.start.time() < dt_time(15, 30)]
        if trough is not None:
            lows.append(trough)
        result["first_candle_low_break"] = any(low < first.low for low in lows)
        level = (_float_or_none(daily.get("previous_low")) if daily
                 and daily.get("session_date") == first.start.date().isoformat() else None)
        result["previous_day_low_break"] = bool(level and level > 0 and min([first.low, *lows]) < level)
        return result

    def _row(self, state: StockState) -> dict[str, Any]:
        candle = state.completed_candle
        opening_candles = self._opening_window_candles(state.opening_candles)
        first_opening = self._first_opening_candle(opening_candles)
        second_opening = next((item for item in opening_candles if first_opening and item.start == first_opening.end), None)
        return {
            **self._redwala_breaks(state.confirmed_opening_candle,
                list(state.confirmed_session_candles.values()), state.daily_filter, state.redwala_gira,
                state.post_opening_trough if state.confirmed_opening_candle
                and state.post_opening_trough_session == state.confirmed_opening_candle.start.date() else None),
            "preparation_status": state.preparation_status,
            "retest_break": state.retest_break,
            "retest_break_at": state.retest_break_at,
            "retest_status": state.retest_status,
            "retest_reason": state.retest_reason,
            "first_candle_high_break": bool(state.possible_candidate and state.confirmed_opening_candle
                and (first_high_broken(state.confirmed_opening_candle, list(state.confirmed_session_candles.values()))
                     or (state.post_opening_peak_session == state.confirmed_opening_candle.start.date()
                         and state.post_opening_peak is not None and state.post_opening_peak > state.confirmed_opening_candle.high))),
            "confirmation_status": state.confirmation_status,
            "provisional_setup": state.provisional_setup,
            "awaiting_confirmation": bool(state.provisional_setup and state.confirmation_status != "confirmed"),
            "required_opening_volume": self.volume_filters.minute_volume_min * state.opening_volume_average if state.opening_volume_average else None,
            "feed_complete": self._live_opening_complete(state, datetime.now(IST).date()),
            **self._circuit_fields(state),
            **self._previous_day_crosses(first_opening, state.daily_filter, state.signal_session,
                                        state.possible_candidate, state.redwala_gira),
            "previous_day_low_cross_second_candle": self._second_candle_pdl_cross(
                first_opening, opening_candles, state.daily_filter, state.signal_session, state.redwala_gira),
            "symbol": state.instrument.symbol,
            "name": state.instrument.name,
            "security_id": state.instrument.security_id,
            "previous_close": state.previous_close,
            "ltp": state.ltp,
            "percent_change": state.percent_change,
            "candle_start": candle.start.isoformat(timespec="seconds") if candle else None,
            "candle_end": candle.end.isoformat(timespec="seconds") if candle else None,
            "candle_open": candle.open if candle else None,
            "candle_high": candle.high if candle else None,
            "candle_low": candle.low if candle else None,
            "candle_close": candle.close if candle else None,
            "candle_volume": candle.volume if candle else 0,
            "candle_turnover": candle.turnover if candle else 0.0,
            "day_volume": state.day_volume,
            "last_tick_time": state.last_tick_time.isoformat(timespec="seconds") if state.last_tick_time else None,
            "opening_volume_average": state.opening_volume_average,
            "opening_volume_samples": state.opening_volume_samples,
            "first_candle_color": first_opening.color if first_opening else None,
            "second_candle_color": second_opening.color if second_opening else None,
            "first_candle_turnover": first_opening.turnover if first_opening else 0.0,
            "opening_candles": [
                {
                    "start": item.start.isoformat(timespec="seconds"),
                    "end": item.end.isoformat(timespec="seconds"),
                    "color": item.color,
                    "close": item.close,
                    "volume": item.volume,
                    "turnover": item.turnover,
                }
                for item in opening_candles
            ],
            "today_opening_volume": state.today_opening_volume,
            "volume_multiplier": state.volume_multiplier,
            "opening_colors_match": state.opening_colors_match,
            "possible_candidate": state.possible_candidate,
            "redwala_gira": state.redwala_gira,
            "qualifies_scan": state.qualifies_scan,
            "daily_filter": state.daily_filter,
            "first_candle_open": first_opening.open if first_opening else None,
            "first_candle_high": first_opening.high if first_opening else None,
            "first_open_equals_high": bool(first_opening and first_opening.open == first_opening.high),
            "first_open_equals_low": bool(first_opening and first_opening.open == first_opening.low),
            "candidate_reason": state.candidate_reason,
            "is_fno": state.instrument.symbol in FNO_SYMBOLS,
            "status": state.status,
            "error": state.error,
        }

    @staticmethod
    def _circuit_fields(state: StockState) -> dict[str, Any]:
        now = datetime.now(IST)
        fresh = (state.circuit_fetched_at is not None
                 and state.circuit_fetched_at.date() == now.date()
                 and (now - state.circuit_fetched_at).total_seconds() <= CIRCUIT_REFRESH_SECONDS * 2)
        upper = state.upper_circuit_limit if fresh else None
        lower = state.lower_circuit_limit if fresh else None
        price = _float_or_none(state.ltp)
        error = state.circuit_error
        upper_distance = lower_distance = None
        if not fresh:
            error = error or "Circuit limits pending or stale"
        elif price is None or price <= 0:
            error = "LTP unavailable"
        elif (upper is not None and price > upper) or (lower is not None and price < lower):
            error = "LTP outside returned circuit limits; awaiting refreshed quote"
        else:
            upper_distance = (upper - price) / price * 100 if upper is not None else None
            lower_distance = (price - lower) / price * 100 if lower is not None else None
        return {
            "upper_circuit_limit": upper,
            "lower_circuit_limit": lower,
            "upper_circuit_distance_percent": upper_distance,
            "lower_circuit_distance_percent": lower_distance,
            "circuit_fetched_at": state.circuit_fetched_at.isoformat(timespec="seconds") if state.circuit_fetched_at else None,
            "circuit_error": error,
        }
