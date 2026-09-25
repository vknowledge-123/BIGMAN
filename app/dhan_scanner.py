from __future__ import annotations

import csv
import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .fno_symbols import FNO_SYMBOLS
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
OPENING_CANDLE_PAIRS = (("09:14", "09:15"), ("09:15", "09:16"))
VOLUME_SAMPLE_COUNT = 3
VOLUME_MULTIPLIER_THRESHOLD = 4.0
CIRCUIT_BANDS = (2.0, 5.0, 10.0, 20.0)


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
    opening_volume_average: float | None = None
    opening_volume_samples: list[dict[str, Any]] = field(default_factory=list)
    today_opening_volume: int | None = None
    volume_multiplier: float | None = None
    opening_colors_match: bool = False
    possible_candidate: bool = False
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
        self._states: dict[str, StockState] = {}
        self._unresolved_symbols: list[str] = []
        self._feed: Any = None
        self._feed_thread: threading.Thread | None = None
        self._candidate_thread: threading.Thread | None = None
        self._candidate_stop = threading.Event()
        self._running = False
        self._connected = False
        self._status = "Idle"

    def load_saved(self) -> None:
        config = self.store.load()
        if config.symbols:
            try:
                self.prepare_symbols(config.symbols)
            except Exception as exc:
                with self._lock:
                    self._states = {}
                    self._unresolved_symbols = config.symbols
                    self._status = f"Could not load saved symbols: {exc}"
                return
            with self._lock:
                for symbol, close in config.previous_closes.items():
                    if symbol in self._states:
                        self._states[symbol].previous_close = close

    def prepare_symbols(self, symbols: list[str]) -> list[str]:
        resolved, unresolved = self.resolver.resolve(symbols)
        config = self.store.load()
        with self._lock:
            self._states = {
                symbol: StockState(
                    instrument=instrument,
                    previous_close=config.previous_closes.get(symbol),
                    opening_volume_average=_float_or_none(
                        config.opening_volume_cache.get(symbol, {}).get("average")
                    ),
                    opening_volume_samples=list(
                        config.opening_volume_cache.get(symbol, {}).get("samples", [])
                    ),
                )
                for symbol, instrument in resolved.items()
            }
            self._unresolved_symbols = unresolved
            self._status = f"Loaded {len(resolved)} symbol(s)"
        return unresolved

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
                if cached or errors:
                    time.sleep(1.15)
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

    def cache_opening_volume_averages(self) -> dict[str, float]:
        client = self._client()
        with self._lock:
            states = list(self._states.values())
        if not states:
            raise RuntimeError("Add stocks first")

        cached: dict[str, float] = {}
        cache_entries: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        fatal_error: str | None = None
        for index, state in enumerate(states):
            if index:
                time.sleep(1.15)
            symbol = state.instrument.symbol
            try:
                samples, today_candles = self._fetch_opening_volume_history(client, state.instrument)
                average = sum(sample["volume"] for sample in samples) / len(samples)
                entry = {
                    "average": average,
                    "samples": samples,
                    "cached_at": datetime.now(IST).isoformat(timespec="seconds"),
                }
                cached[symbol] = average
                cache_entries[symbol] = entry
                with self._lock:
                    target = self._states.get(symbol)
                    if target:
                        target.opening_volume_average = average
                        target.opening_volume_samples = samples
                        target.error = None
                        target.status = "volume cached"
                if self._select_opening_pair(today_candles) is not None:
                    self._apply_opening_candidate(symbol, today_candles)
            except Exception as exc:
                errors[symbol] = str(exc)
                with self._lock:
                    target = self._states.get(symbol)
                    if target:
                        target.error = f"Volume cache failed: {exc}"
                        target.status = "volume cache error"
                if _should_stop_api_batch(exc):
                    fatal_error = str(exc)
                    for remaining in states[index + 1 :]:
                        remaining_symbol = remaining.instrument.symbol
                        errors[remaining_symbol] = f"Skipped after Dhan error: {exc}"
                        with self._lock:
                            target = self._states.get(remaining_symbol)
                            if target:
                                target.error = errors[remaining_symbol]
                                target.status = "volume cache skipped"
                    break

        if cache_entries:
            self.store.update_opening_volume_cache(cache_entries)

        with self._lock:
            self._status = f"Cached 3-day opening volume average for {len(cached)} stock(s)"
            if errors:
                self._status += f"; {len(errors)} error(s)"
        if not cached and fatal_error:
            raise RuntimeError(fatal_error)
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
                    candle for candle in all_candles.values() if candle.start.date() == now.date()
                ]
                return samples, today_candles
            cursor_end = window_start
            time.sleep(1.15)

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

    def evaluate_opening_candidates(self, client: Any | None = None) -> int:
        client = client or self._client()
        with self._lock:
            states = list(self._states.values())

        candidate_count = 0
        checked_count = 0
        first_error: str | None = None
        for index, state in enumerate(states):
            if index:
                time.sleep(1.15)
            symbol = state.instrument.symbol
            try:
                candles = self._fetch_opening_candles(client, state.instrument)
                is_candidate = self._apply_opening_candidate(symbol, candles)
                checked_count += 1
                if is_candidate:
                    candidate_count += 1
            except Exception as exc:
                first_error = first_error or str(exc)
                with self._lock:
                    target = self._states.get(symbol)
                    if target:
                        target.possible_candidate = False
                        target.candidate_reason = f"Opening candle check failed: {exc}"
                if _should_stop_api_batch(exc):
                    for remaining in states[index + 1 :]:
                        with self._lock:
                            target = self._states.get(remaining.instrument.symbol)
                            if target:
                                target.possible_candidate = False
                                target.candidate_reason = f"Opening candle check skipped: {exc}"
                    break
        if states and checked_count == 0 and first_error:
            raise RuntimeError(first_error)
        return candidate_count

    def _apply_opening_candidate(self, symbol: str, candles: list[Candle]) -> bool:
        colors_match, color_reason = self._evaluate_opening_candle_pairs(candles)
        selected_pair = self._select_opening_pair(candles)
        if selected_pair is None:
            raise RuntimeError("Dhan did not return a complete opening candle pair")
        _, first, _, _ = selected_pair

        with self._lock:
            target = self._states.get(symbol)
            if target is None:
                return False
            target.today_opening_volume = first.volume
            average = target.opening_volume_average
            target.volume_multiplier = first.volume / average if average and average > 0 else None
            target.opening_colors_match = colors_match
            meets_volume = (
                target.volume_multiplier is not None
                and target.volume_multiplier >= VOLUME_MULTIPLIER_THRESHOLD
            )
            target.possible_candidate = colors_match and meets_volume
            if target.volume_multiplier is None:
                target.candidate_reason = f"{color_reason}; cache volume average first"
            else:
                target.candidate_reason = (
                    f"{color_reason}; opening volume {first.volume:,} / average {average:,.0f} "
                    f"= {target.volume_multiplier:.2f}x"
                )
            return target.possible_candidate

    def _fetch_opening_candles(self, client: Any, instrument: Instrument) -> list[Candle]:
        today = datetime.now(IST).date()
        session_start = datetime.combine(today, dt_time(9, 14), tzinfo=IST)
        session_end = datetime.combine(today, dt_time(9, 18), tzinfo=IST)
        response = self._intraday_with_retry(
            client,
            instrument.security_id,
            instrument.exchange_segment,
            instrument.instrument_type,
            session_start.strftime("%Y-%m-%d %H:%M:%S"),
            session_end.strftime("%Y-%m-%d %H:%M:%S"),
        )
        return self._parse_intraday_candles(response)

    def _evaluate_opening_candle_pairs(self, candles: list[Candle]) -> tuple[bool, str]:
        selected = self._select_opening_pair(candles)
        if selected is None:
            labels = ", ".join(f"{first}/{second}" for first, second in OPENING_CANDLE_PAIRS)
            raise RuntimeError(f"Dhan did not return opening candle pairs: {labels}")

        first_label, first, second_label, second = selected
        detail = (
            f"{first_label}/{second_label}: {first_label} {first.color}, "
            f"{second_label} {second.color}"
        )
        if self._is_opposite_green_red_pair(first.color, second.color):
            return True, f"Matched {detail}"
        return False, detail

    @staticmethod
    def _select_opening_pair(
        candles: list[Candle],
    ) -> tuple[str, Candle, str, Candle] | None:
        by_minute = {candle.start.strftime("%H:%M"): candle for candle in candles}
        for first_label, second_label in OPENING_CANDLE_PAIRS:
            first = by_minute.get(first_label)
            second = by_minute.get(second_label)
            if first is not None and second is not None:
                return first_label, first, second_label, second
        return None

    @staticmethod
    def _is_opposite_green_red_pair(first_color: str, second_color: str) -> bool:
        return {first_color, second_color} == {"green", "red"}

    def _parse_intraday_candles(self, response: Any) -> list[Candle]:
        data = _extract_data(response)
        timestamps = data.get("timestamp") or []
        opens = data.get("open") or []
        highs = data.get("high") or []
        lows = data.get("low") or []
        closes = data.get("close") or []
        volumes = data.get("volume") or []
        candles: list[Candle] = []
        for index, ts in enumerate(timestamps):
            try:
                candle_start = datetime.fromtimestamp(int(float(ts)), IST).replace(second=0, microsecond=0)
                candles.append(
                    Candle(
                        start=candle_start,
                        open=float(opens[index]),
                        high=float(highs[index]),
                        low=float(lows[index]),
                        close=float(closes[index]),
                        volume=int(float(volumes[index])),
                    )
                )
            except (IndexError, TypeError, ValueError):
                continue
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
            response = client.ohlc_data(securities)
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
                response = client.historical_daily_data(*args)
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
            response = client.intraday_minute_data(*args, interval=1, oi=False)
            if isinstance(response, dict) and response.get("status") == "failure":
                last_error = _format_dhan_error(response.get("remarks"))
                if "DH-904" in last_error or "Rate_Limit" in last_error:
                    if attempt < 2:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    raise RuntimeError(last_error)
            return response
        raise RuntimeError(last_error or "Dhan intraday request failed")

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
            states = list(self._states.values())
            self._running = True
            self._connected = False
            self._status = "Connecting to Dhan websocket..."

        instruments = [
            (MarketFeed.NSE, state.instrument.security_id, MarketFeed.Quote)
            for state in states
        ]
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
        self._candidate_thread = threading.Thread(
            target=self._refresh_opening_candidates_when_ready,
            args=(self._candidate_stop,),
            name="opening-candidate-refresh",
            daemon=True,
        )
        self._candidate_thread.start()

    def stop(self) -> None:
        feed = self._feed
        self._candidate_stop.set()
        with self._lock:
            self._running = False
            self._connected = False
            self._feed = None
            self._feed_thread = None
            self._candidate_thread = None
            if self._status != "Idle":
                self._status = "Stopped"
        if feed is not None:
            try:
                feed.close_connection()
            except Exception as exc:
                LOGGER.warning("Error closing Dhan feed: %s", exc)

    def _refresh_opening_candidates_when_ready(self, stop_event: threading.Event) -> None:
        now = datetime.now(IST)
        ready_at = datetime.combine(now.date(), dt_time(9, 17), tzinfo=IST)
        wait_seconds = max((ready_at - now).total_seconds(), 0)
        if stop_event.wait(wait_seconds):
            return
        with self._lock:
            already_checked = bool(self._states) and all(
                state.today_opening_volume is not None for state in self._states.values()
            )
        if already_checked:
            return
        try:
            count = self.evaluate_opening_candidates()
            with self._lock:
                if self._running:
                    self._status = f"Live feed connected; {count} possible candidate(s)"
        except Exception as exc:
            LOGGER.warning("Automatic opening candidate refresh failed: %s", exc)

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
        response = client.intraday_minute_data(
            instrument.security_id,
            instrument.exchange_segment,
            instrument.instrument_type,
            start.strftime("%Y-%m-%d %H:%M:%S"),
            (end + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
            interval=1,
            oi=False,
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
                    state.status = "repaired"
                    repaired += 1
        return repaired

    def _on_connect(self, _feed: Any) -> None:
        with self._lock:
            self._connected = True
            self._status = "Live feed connected"
            for state in self._states.values():
                state.status = "live"

    def _on_close(self, _feed: Any) -> None:
        with self._lock:
            self._connected = False
            if self._running:
                self._status = "Live feed disconnected"

    def _on_error(self, _feed: Any, error: Exception) -> None:
        with self._lock:
            self._connected = False
            self._status = f"Feed error: {error}"

    def _on_message(self, _feed: Any, data: Any) -> None:
        if not isinstance(data, dict):
            return
        security_id = str(data.get("security_id", ""))
        with self._lock:
            symbol = next(
                (
                    key
                    for key, value in self._states.items()
                    if value.instrument.security_id == security_id
                ),
                None,
            )
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
            state.status = "live"
            state.error = None
            if state.previous_close:
                state.percent_change = ((ltp - state.previous_close) / state.previous_close) * 100

            volume_delta = 0
            if cumulative_volume is not None:
                if state.last_cumulative_volume is not None and cumulative_volume >= state.last_cumulative_volume:
                    volume_delta = cumulative_volume - state.last_cumulative_volume
                state.last_cumulative_volume = cumulative_volume

            if state.current_candle is None:
                state.current_candle = Candle(candle_start, ltp, ltp, ltp, ltp, volume_delta)
                return

            if candle_start == state.current_candle.start:
                state.current_candle.update(ltp, volume_delta)
                return

            if candle_start > state.current_candle.start:
                state.completed_candle = state.current_candle
                state.current_candle = Candle(candle_start, ltp, ltp, ltp, ltp, volume_delta)
                return

            state.current_candle.update(ltp, volume_delta)

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
                "connected": self._connected,
                "status": self._status,
                "stocks": rows,
                "unresolved_symbols": list(self._unresolved_symbols),
                "updated_at": datetime.now(IST).isoformat(timespec="seconds"),
            }

    def _row(self, state: StockState) -> dict[str, Any]:
        candle = state.completed_candle
        return {
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
            "today_opening_volume": state.today_opening_volume,
            "volume_multiplier": state.volume_multiplier,
            "opening_colors_match": state.opening_colors_match,
            "possible_candidate": state.possible_candidate,
            "candidate_reason": state.candidate_reason,
            "is_fno": state.instrument.symbol in FNO_SYMBOLS,
            "status": state.status,
            "error": state.error,
        }
