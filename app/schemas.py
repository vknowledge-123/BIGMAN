from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CredentialsIn(BaseModel):
    client_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)


class SymbolsIn(BaseModel):
    symbols_text: str = ""


class BacktestIn(BaseModel):
    target_date: date


class MessageOut(BaseModel):
    ok: bool
    message: str


class ConfigOut(BaseModel):
    has_credentials: bool
    client_id: str
    symbols_text: str
    cached_close_count: int
    cached_volume_count: int


class DailyVolumeFilter(BaseModel):
    session_date: str
    previous_date: str
    previous_volume: int
    previous_close: float
    prior_close: float
    average: float
    multiplier: float
    percent_change: float
    samples: list[dict]
    passes: bool
    price_exception: bool


class QualificationFields(BaseModel):
    daily_filter: DailyVolumeFilter | None = None
    redwala_gira: bool = False
    qualifies_scan: bool = False
    first_candle_open: float | None = None
    first_candle_high: float | None = None
    first_open_equals_high: bool = False


class StockRow(QualificationFields):
    upper_circuit_limit: float | None = None
    lower_circuit_limit: float | None = None
    upper_circuit_distance_percent: float | None = None
    lower_circuit_distance_percent: float | None = None
    circuit_fetched_at: str | None = None
    circuit_error: str | None = None
    symbol: str
    name: str | None = None
    security_id: str | None = None
    previous_close: float | None = None
    ltp: float | None = None
    percent_change: float | None = None
    candle_start: str | None = None
    candle_end: str | None = None
    candle_open: float | None = None
    candle_high: float | None = None
    candle_low: float | None = None
    candle_close: float | None = None
    candle_volume: int = 0
    candle_turnover: float = 0.0
    day_volume: int | None = None
    last_tick_time: str | None = None
    opening_volume_average: float | None = None
    opening_volume_samples: list[dict] = Field(default_factory=list)
    first_candle_color: str | None = None
    second_candle_color: str | None = None
    first_candle_turnover: float = 0.0
    opening_candles: list[dict] = Field(default_factory=list)
    today_opening_volume: int | None = None
    volume_multiplier: float | None = None
    opening_colors_match: bool = False
    possible_candidate: bool = False
    candidate_reason: str | None = None
    is_fno: bool = False
    status: str = "waiting"
    error: str | None = None


class StateOut(BaseModel):
    running: bool
    connected: bool
    status: str
    stocks: list[StockRow]
    unresolved_symbols: list[str]
    updated_at: str


class BacktestRow(QualificationFields):
    symbol: str
    name: str
    security_id: str
    target_date: str
    first_candle_start: str | None = None
    first_candle_color: str | None = None
    second_candle_start: str | None = None
    second_candle_color: str | None = None
    first_candle_volume: int | None = None
    opening_volume_average: float | None = None
    opening_volume_samples: list[dict] = Field(default_factory=list)
    volume_multiplier: float | None = None
    opening_colors_match: bool = False
    possible_candidate: bool = False
    candidate_reason: str | None = None
    is_fno: bool = False
    status: str = "waiting"
    error: str | None = None


class BacktestOut(BaseModel):
    target_date: str
    stocks: list[BacktestRow]
    tested_count: int
    four_x_count: int
    candidate_count: int
    qualified_count: int = 0
    redwala_count: int = 0
    error_count: int
