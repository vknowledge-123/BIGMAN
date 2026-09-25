from __future__ import annotations

from pydantic import BaseModel, Field


class CredentialsIn(BaseModel):
    client_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)


class SymbolsIn(BaseModel):
    symbols_text: str = ""


class MessageOut(BaseModel):
    ok: bool
    message: str


class ConfigOut(BaseModel):
    has_credentials: bool
    client_id: str
    symbols_text: str
    cached_close_count: int
    cached_volume_count: int


class StockRow(BaseModel):
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
