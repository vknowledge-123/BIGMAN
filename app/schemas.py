from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VolumeFilterSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    daily_volume_max: float = Field(default=4.0, gt=0, allow_inf_nan=False)
    minute_volume_min: float = Field(default=4.0, gt=0, allow_inf_nan=False)
    first_candle_turnover_min: float = Field(default=30_000_000, gt=0, allow_inf_nan=False)  # INR
    today_open_cross: bool = False
    monthly_filter: bool = False
    last_two_days_filter: bool = False


class CredentialsIn(BaseModel):
    client_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)


class SymbolsIn(BaseModel):
    symbols_text: str = ""


class BacktestIn(BaseModel):
    target_date: date
    scan_type: Literal["opening"] = "opening"


class MessageOut(BaseModel):
    ok: bool
    message: str


class ConfigOut(BaseModel):
    volume_filters: VolumeFilterSettings = Field(default_factory=VolumeFilterSettings)
    has_credentials: bool
    client_id: str
    symbols_text: str
    cached_close_count: int
    cached_volume_count: int


class DailyVolumeFilter(BaseModel):
    twenty_day_closes: list[dict] = Field(default_factory=list)
    last_two_day_candles: list[dict] = Field(default_factory=list)
    five_day_highest_close: float | None = None
    five_day_closes: list[dict] = Field(default_factory=list)
    volume_limit: float = 4.0
    session_date: str
    previous_date: str
    previous_volume: int
    previous_close: float
    previous_high: float | None = None
    previous_low: float | None = None
    prior_close: float
    average: float
    multiplier: float
    percent_change: float
    samples: list[dict]
    passes: bool
    price_exception: bool


class QualificationFields(BaseModel):
    first_candle_high_break: bool = False
    first_candle_low_break: bool = False
    previous_day_low_break: bool = False
    retest_break: bool = False
    retest_break_at: str | None = None
    retest_status: str = "waiting"
    retest_reason: str | None = None
    daily_filter: DailyVolumeFilter | None = None
    redwala_gira: bool = False
    qualifies_scan: bool = False
    first_candle_open: float | None = None
    first_candle_high: float | None = None
    first_open_equals_high: bool = False
    first_open_equals_low: bool = False
    previous_day_high_cross: bool = False
    previous_day_low_cross: bool = False
    previous_day_low_cross_second_candle: bool = False


class StockRow(QualificationFields):
    preparation_status: str = "unresolved"
    confirmation_status: str = "pending"
    provisional_setup: str | None = None
    awaiting_confirmation: bool = False
    required_opening_volume: float | None = None
    feed_complete: bool = False
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
    volume_filters: VolumeFilterSettings = Field(default_factory=VolumeFilterSettings)
    running: bool
    connected: bool
    status: str
    stocks: list[StockRow]
    unresolved_symbols: list[str]
    updated_at: str


class BacktestRow(QualificationFields):
    data_warning: str | None = None
    symbol: str
    name: str
    security_id: str
    target_date: str
    first_candle_start: str | None = None
    first_candle_color: str | None = None
    second_candle_start: str | None = None
    second_candle_color: str | None = None
    first_candle_volume: int | None = None
    first_candle_turnover: float = 0.0
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
    warning_count: int = 0
    scan_type: str = "opening"
    volume_filters: VolumeFilterSettings = Field(default_factory=VolumeFilterSettings)
    target_date: str
    stocks: list[BacktestRow]
    tested_count: int
    four_x_count: int
    candidate_count: int
    qualified_count: int = 0
    redwala_count: int = 0
    retest_count: int = 0
    error_count: int
