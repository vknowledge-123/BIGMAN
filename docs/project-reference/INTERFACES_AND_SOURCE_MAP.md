# Interfaces and source map

Generated from the main source on 8 November 2026. No runtime account or cache data was read.

This file complements PROJECT_SPECIFICATION.md. Line references identify this snapshot and can change after edits.

## HTTP route inventory

| Method | Path | Handler parameters | Response model | Source |
|---|---|---|---|---|
| GET | `/` | `dashboard()` | `dynamic / HTML` | app/main.py:57 |
| GET | `/api/config` | `get_config()` | `ConfigOut` | app/main.py:69 |
| POST | `/api/volume-filters` | `save_volume_filters(payload: VolumeFilterSettings)` | `MessageOut` | app/main.py:82 |
| POST | `/api/credentials` | `save_credentials(payload: CredentialsIn)` | `MessageOut` | app/main.py:87 |
| POST | `/api/symbols` | `save_symbols(payload: SymbolsIn)` | `MessageOut` | app/main.py:96 |
| GET | `/api/preopen` | `get_preopen_import()` | `dynamic / HTML` | app/main.py:114 |
| POST | `/api/preopen/preview` | `preview_preopen(payload: PreopenRequest)` | `dynamic / HTML` | app/main.py:119 |
| POST | `/api/preopen/apply` | `apply_preopen(payload: PreopenRequest)` | `dynamic / HTML` | app/main.py:127 |
| POST | `/api/cache` | `cache_data()` | `MessageOut` | app/main.py:144 |
| POST | `/api/cache-volume` | `cache_volume_average()` | `MessageOut` | app/main.py:153 |
| POST | `/api/backtest` | `run_backtest(payload: BacktestIn)` | `BacktestOut` | app/main.py:165 |
| POST | `/api/start` | `start_scan()` | `MessageOut` | app/main.py:179 |
| POST | `/api/stop` | `stop_scan()` | `MessageOut` | app/main.py:188 |
| POST | `/api/repair` | `repair_missing()` | `MessageOut` | app/main.py:194 |
| GET | `/api/state` | `get_state()` | `StateOut` | app/main.py:210 |
| POST | `/api/algo/settings` | `save_algo_settings(payload: AlgoSettings)` | `MessageOut` | app/main.py:215 |
| POST | `/api/algo/start` | `start_algo(payload: AlgoStart)` | `dynamic / HTML` | app/main.py:221 |
| POST | `/api/algo/{session_id}/exit` | `exit_algo(session_id: str)` | `MessageOut` | app/main.py:230 |
| POST | `/api/algo/{session_id}/resume` | `resume_algo(session_id: str)` | `MessageOut` | app/main.py:239 |
| POST | `/api/algo/backtest` | `backtest_algo(payload: AlgoBacktest)` | `dynamic / HTML` | app/main.py:248 |

FastAPI also serves its standard /docs, /redoc and /openapi.json surfaces. Static resources are mounted at /static.

## Exact model field inventory

The JSON schema sidecar is authoritative for validation constraints and unions. Fields inherited from base models are included below. These are code defaults, not saved account settings.

### VolumeFilterSettings

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `daily_volume_max` | `<class 'float'>` | `4.0` | `[Gt(gt=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `minute_volume_min` | `<class 'float'>` | `4.0` | `[Gt(gt=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `first_candle_turnover_min` | `<class 'float'>` | `30000000` | `[Gt(gt=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `today_open_cross` | `<class 'bool'>` | `False` | `[]` |
| `monthly_filter` | `<class 'bool'>` | `False` | `[]` |
| `last_two_days_filter` | `<class 'bool'>` | `False` | `[]` |
| `redwala_open_previous_close` | `<class 'bool'>` | `False` | `[]` |
| `redwala_open_gap_max` | `<class 'float'>` | `1.0` | `[Ge(ge=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `redwala_open_tolerance` | `<class 'bool'>` | `False` | `[]` |
| `redwala_open_tolerance_max` | `<class 'float'>` | `0.5` | `[Ge(ge=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `pdhl_filter` | `<class 'bool'>` | `False` | `[]` |
| `pdhl_max` | `<class 'float'>` | `4.0` | `[Ge(ge=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `possible_open_pre_close` | `<class 'bool'>` | `False` | `[]` |
| `possible_open_pre_close_max` | `<class 'float'>` | `1.0` | `[Ge(ge=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `resistance_filter` | `<class 'bool'>` | `False` | `[]` |
| `resistance_lookback` | `<class 'int'>` | `60` | `[Ge(ge=5), Le(le=252)]` |
| `resistance_left` | `<class 'int'>` | `2` | `[Ge(ge=1), Le(le=10)]` |
| `resistance_right` | `<class 'int'>` | `2` | `[Ge(ge=1), Le(le=10)]` |
| `resistance_min_age` | `<class 'int'>` | `4` | `[Ge(ge=1), Le(le=252)]` |
| `resistance_max_age` | `<class 'int'>` | `60` | `[Ge(ge=1), Le(le=252)]` |
| `resistance_buffer` | `<class 'float'>` | `0` | `[Ge(ge=0), Le(le=100), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `resistance_pullback` | `<class 'bool'>` | `False` | `[]` |
| `resistance_pullback_min` | `<class 'float'>` | `3` | `[Ge(ge=0), Le(le=100), _PydanticGeneralMetadata(allow_inf_nan=False)]` |

### CredentialsIn

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `client_id` | `<class 'str'>` | `REQUIRED` | `[MinLen(min_length=1)]` |
| `access_token` | `<class 'str'>` | `''` | `[]` |

### SymbolsIn

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `symbols_text` | `<class 'str'>` | `''` | `[]` |

### BacktestIn

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `target_date` | `<class 'datetime.date'>` | `REQUIRED` | `[]` |
| `scan_type` | `typing.Literal['opening']` | `'opening'` | `[]` |
| `volume_filters` | `app.schemas.VolumeFilterSettings \| None` | `None` | `[]` |

### MessageOut

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `ok` | `<class 'bool'>` | `REQUIRED` | `[]` |
| `message` | `<class 'str'>` | `REQUIRED` | `[]` |

### ConfigOut

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `volume_filters` | `<class 'app.schemas.VolumeFilterSettings'>` | `factory: VolumeFilterSettings` | `[]` |
| `has_credentials` | `<class 'bool'>` | `REQUIRED` | `[]` |
| `client_id` | `<class 'str'>` | `REQUIRED` | `[]` |
| `symbols_text` | `<class 'str'>` | `REQUIRED` | `[]` |
| `cached_close_count` | `<class 'int'>` | `REQUIRED` | `[]` |
| `cached_volume_count` | `<class 'int'>` | `REQUIRED` | `[]` |

### DailyVolumeFilter

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `twenty_day_closes` | `list[dict]` | `factory: list` | `[]` |
| `last_two_day_candles` | `list[dict]` | `factory: list` | `[]` |
| `five_day_highest_close` | `float \| None` | `None` | `[]` |
| `five_day_closes` | `list[dict]` | `factory: list` | `[]` |
| `volume_limit` | `<class 'float'>` | `4.0` | `[]` |
| `session_date` | `<class 'str'>` | `REQUIRED` | `[]` |
| `previous_date` | `<class 'str'>` | `REQUIRED` | `[]` |
| `previous_volume` | `<class 'int'>` | `REQUIRED` | `[]` |
| `previous_close` | `<class 'float'>` | `REQUIRED` | `[]` |
| `previous_high` | `float \| None` | `None` | `[]` |
| `previous_low` | `float \| None` | `None` | `[]` |
| `prior_close` | `<class 'float'>` | `REQUIRED` | `[]` |
| `average` | `<class 'float'>` | `REQUIRED` | `[]` |
| `multiplier` | `<class 'float'>` | `REQUIRED` | `[]` |
| `percent_change` | `<class 'float'>` | `REQUIRED` | `[]` |
| `samples` | `list[dict]` | `REQUIRED` | `[]` |
| `passes` | `<class 'bool'>` | `REQUIRED` | `[]` |
| `price_exception` | `<class 'bool'>` | `REQUIRED` | `[]` |

### QualificationFields

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `resistance_level` | `float \| None` | `None` | `[]` |
| `resistance_threshold` | `float \| None` | `None` | `[]` |
| `resistance_date` | `str \| None` | `None` | `[]` |
| `resistance_age` | `int \| None` | `None` | `[]` |
| `resistance_pullback_percent` | `float \| None` | `None` | `[]` |
| `resistance_status` | `<class 'str'>` | `'off'` | `[]` |
| `resistance_break` | `<class 'bool'>` | `False` | `[]` |
| `resistance_break_open` | `<class 'bool'>` | `False` | `[]` |
| `resistance_break_open_candle` | `int \| None` | `None` | `[]` |
| `resistance_break_at` | `str \| None` | `None` | `[]` |
| `first_candle_high_break` | `<class 'bool'>` | `False` | `[]` |
| `first_candle_low_break` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_low_break` | `<class 'bool'>` | `False` | `[]` |
| `retest_break` | `<class 'bool'>` | `False` | `[]` |
| `retest_break_at` | `str \| None` | `None` | `[]` |
| `retest_status` | `<class 'str'>` | `'waiting'` | `[]` |
| `retest_reason` | `str \| None` | `None` | `[]` |
| `daily_filter` | `app.schemas.DailyVolumeFilter \| None` | `None` | `[]` |
| `redwala_gira` | `<class 'bool'>` | `False` | `[]` |
| `qualifies_scan` | `<class 'bool'>` | `False` | `[]` |
| `first_candle_open` | `float \| None` | `None` | `[]` |
| `first_candle_close` | `float \| None` | `None` | `[]` |
| `first_candle_high` | `float \| None` | `None` | `[]` |
| `first_open_equals_high` | `<class 'bool'>` | `False` | `[]` |
| `first_open_equals_low` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_high_cross` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_low_cross` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_low_cross_second_candle` | `<class 'bool'>` | `False` | `[]` |

### StockRow

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `resistance_level` | `float \| None` | `None` | `[]` |
| `resistance_threshold` | `float \| None` | `None` | `[]` |
| `resistance_date` | `str \| None` | `None` | `[]` |
| `resistance_age` | `int \| None` | `None` | `[]` |
| `resistance_pullback_percent` | `float \| None` | `None` | `[]` |
| `resistance_status` | `<class 'str'>` | `'off'` | `[]` |
| `resistance_break` | `<class 'bool'>` | `False` | `[]` |
| `resistance_break_open` | `<class 'bool'>` | `False` | `[]` |
| `resistance_break_open_candle` | `int \| None` | `None` | `[]` |
| `resistance_break_at` | `str \| None` | `None` | `[]` |
| `first_candle_high_break` | `<class 'bool'>` | `False` | `[]` |
| `first_candle_low_break` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_low_break` | `<class 'bool'>` | `False` | `[]` |
| `retest_break` | `<class 'bool'>` | `False` | `[]` |
| `retest_break_at` | `str \| None` | `None` | `[]` |
| `retest_status` | `<class 'str'>` | `'waiting'` | `[]` |
| `retest_reason` | `str \| None` | `None` | `[]` |
| `daily_filter` | `app.schemas.DailyVolumeFilter \| None` | `None` | `[]` |
| `redwala_gira` | `<class 'bool'>` | `False` | `[]` |
| `qualifies_scan` | `<class 'bool'>` | `False` | `[]` |
| `first_candle_open` | `float \| None` | `None` | `[]` |
| `first_candle_close` | `float \| None` | `None` | `[]` |
| `first_candle_high` | `float \| None` | `None` | `[]` |
| `first_open_equals_high` | `<class 'bool'>` | `False` | `[]` |
| `first_open_equals_low` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_high_cross` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_low_cross` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_low_cross_second_candle` | `<class 'bool'>` | `False` | `[]` |
| `preparation_status` | `<class 'str'>` | `'unresolved'` | `[]` |
| `confirmation_status` | `<class 'str'>` | `'pending'` | `[]` |
| `provisional_setup` | `str \| None` | `None` | `[]` |
| `awaiting_confirmation` | `<class 'bool'>` | `False` | `[]` |
| `required_opening_volume` | `float \| None` | `None` | `[]` |
| `feed_complete` | `<class 'bool'>` | `False` | `[]` |
| `upper_circuit_limit` | `float \| None` | `None` | `[]` |
| `lower_circuit_limit` | `float \| None` | `None` | `[]` |
| `upper_circuit_distance_percent` | `float \| None` | `None` | `[]` |
| `lower_circuit_distance_percent` | `float \| None` | `None` | `[]` |
| `circuit_fetched_at` | `str \| None` | `None` | `[]` |
| `circuit_error` | `str \| None` | `None` | `[]` |
| `circuit_reference_close` | `float \| None` | `None` | `[]` |
| `circuit_band_percent` | `float \| None` | `None` | `[]` |
| `circuit_band_status` | `<class 'str'>` | `'unverified'` | `[]` |
| `circuit_band_eligible` | `<class 'bool'>` | `False` | `[]` |
| `symbol` | `<class 'str'>` | `REQUIRED` | `[]` |
| `name` | `str \| None` | `None` | `[]` |
| `security_id` | `str \| None` | `None` | `[]` |
| `previous_close` | `float \| None` | `None` | `[]` |
| `ltp` | `float \| None` | `None` | `[]` |
| `percent_change` | `float \| None` | `None` | `[]` |
| `candle_start` | `str \| None` | `None` | `[]` |
| `candle_end` | `str \| None` | `None` | `[]` |
| `candle_open` | `float \| None` | `None` | `[]` |
| `candle_high` | `float \| None` | `None` | `[]` |
| `candle_low` | `float \| None` | `None` | `[]` |
| `candle_close` | `float \| None` | `None` | `[]` |
| `candle_volume` | `<class 'int'>` | `0` | `[]` |
| `candle_turnover` | `<class 'float'>` | `0.0` | `[]` |
| `day_volume` | `int \| None` | `None` | `[]` |
| `last_tick_time` | `str \| None` | `None` | `[]` |
| `opening_volume_average` | `float \| None` | `None` | `[]` |
| `opening_volume_samples` | `list[dict]` | `factory: list` | `[]` |
| `first_candle_color` | `str \| None` | `None` | `[]` |
| `second_candle_color` | `str \| None` | `None` | `[]` |
| `first_candle_turnover` | `<class 'float'>` | `0.0` | `[]` |
| `opening_candles` | `list[dict]` | `factory: list` | `[]` |
| `today_opening_volume` | `int \| None` | `None` | `[]` |
| `volume_multiplier` | `float \| None` | `None` | `[]` |
| `opening_colors_match` | `<class 'bool'>` | `False` | `[]` |
| `possible_candidate` | `<class 'bool'>` | `False` | `[]` |
| `candidate_reason` | `str \| None` | `None` | `[]` |
| `is_fno` | `<class 'bool'>` | `False` | `[]` |
| `status` | `<class 'str'>` | `'waiting'` | `[]` |
| `error` | `str \| None` | `None` | `[]` |

### StateOut

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `algo` | `<class 'dict'>` | `factory: dict` | `[]` |
| `volume_filters` | `<class 'app.schemas.VolumeFilterSettings'>` | `factory: VolumeFilterSettings` | `[]` |
| `running` | `<class 'bool'>` | `REQUIRED` | `[]` |
| `connected` | `<class 'bool'>` | `REQUIRED` | `[]` |
| `status` | `<class 'str'>` | `REQUIRED` | `[]` |
| `stocks` | `list[app.schemas.StockRow]` | `REQUIRED` | `[]` |
| `unresolved_symbols` | `list[str]` | `REQUIRED` | `[]` |
| `updated_at` | `<class 'str'>` | `REQUIRED` | `[]` |

### BacktestRow

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `resistance_level` | `float \| None` | `None` | `[]` |
| `resistance_threshold` | `float \| None` | `None` | `[]` |
| `resistance_date` | `str \| None` | `None` | `[]` |
| `resistance_age` | `int \| None` | `None` | `[]` |
| `resistance_pullback_percent` | `float \| None` | `None` | `[]` |
| `resistance_status` | `<class 'str'>` | `'off'` | `[]` |
| `resistance_break` | `<class 'bool'>` | `False` | `[]` |
| `resistance_break_open` | `<class 'bool'>` | `False` | `[]` |
| `resistance_break_open_candle` | `int \| None` | `None` | `[]` |
| `resistance_break_at` | `str \| None` | `None` | `[]` |
| `first_candle_high_break` | `<class 'bool'>` | `False` | `[]` |
| `first_candle_low_break` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_low_break` | `<class 'bool'>` | `False` | `[]` |
| `retest_break` | `<class 'bool'>` | `False` | `[]` |
| `retest_break_at` | `str \| None` | `None` | `[]` |
| `retest_status` | `<class 'str'>` | `'waiting'` | `[]` |
| `retest_reason` | `str \| None` | `None` | `[]` |
| `daily_filter` | `app.schemas.DailyVolumeFilter \| None` | `None` | `[]` |
| `redwala_gira` | `<class 'bool'>` | `False` | `[]` |
| `qualifies_scan` | `<class 'bool'>` | `False` | `[]` |
| `first_candle_open` | `float \| None` | `None` | `[]` |
| `first_candle_close` | `float \| None` | `None` | `[]` |
| `first_candle_high` | `float \| None` | `None` | `[]` |
| `first_open_equals_high` | `<class 'bool'>` | `False` | `[]` |
| `first_open_equals_low` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_high_cross` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_low_cross` | `<class 'bool'>` | `False` | `[]` |
| `previous_day_low_cross_second_candle` | `<class 'bool'>` | `False` | `[]` |
| `data_warning` | `str \| None` | `None` | `[]` |
| `symbol` | `<class 'str'>` | `REQUIRED` | `[]` |
| `name` | `<class 'str'>` | `REQUIRED` | `[]` |
| `security_id` | `<class 'str'>` | `REQUIRED` | `[]` |
| `target_date` | `<class 'str'>` | `REQUIRED` | `[]` |
| `first_candle_start` | `str \| None` | `None` | `[]` |
| `first_candle_color` | `str \| None` | `None` | `[]` |
| `second_candle_start` | `str \| None` | `None` | `[]` |
| `second_candle_color` | `str \| None` | `None` | `[]` |
| `first_candle_volume` | `int \| None` | `None` | `[]` |
| `first_candle_turnover` | `<class 'float'>` | `0.0` | `[]` |
| `opening_volume_average` | `float \| None` | `None` | `[]` |
| `opening_volume_samples` | `list[dict]` | `factory: list` | `[]` |
| `volume_multiplier` | `float \| None` | `None` | `[]` |
| `opening_colors_match` | `<class 'bool'>` | `False` | `[]` |
| `possible_candidate` | `<class 'bool'>` | `False` | `[]` |
| `candidate_reason` | `str \| None` | `None` | `[]` |
| `is_fno` | `<class 'bool'>` | `False` | `[]` |
| `status` | `<class 'str'>` | `'waiting'` | `[]` |
| `error` | `str \| None` | `None` | `[]` |

### BacktestOut

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `warning_count` | `<class 'int'>` | `0` | `[]` |
| `scan_type` | `<class 'str'>` | `'opening'` | `[]` |
| `volume_filters` | `<class 'app.schemas.VolumeFilterSettings'>` | `factory: VolumeFilterSettings` | `[]` |
| `target_date` | `<class 'str'>` | `REQUIRED` | `[]` |
| `stocks` | `list[app.schemas.BacktestRow]` | `REQUIRED` | `[]` |
| `tested_count` | `<class 'int'>` | `REQUIRED` | `[]` |
| `four_x_count` | `<class 'int'>` | `REQUIRED` | `[]` |
| `candidate_count` | `<class 'int'>` | `REQUIRED` | `[]` |
| `qualified_count` | `<class 'int'>` | `0` | `[]` |
| `redwala_count` | `<class 'int'>` | `0` | `[]` |
| `retest_count` | `<class 'int'>` | `0` | `[]` |
| `error_count` | `<class 'int'>` | `REQUIRED` | `[]` |

### PreopenSettings

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `universe` | `typing.Literal['cash', 'fno']` | `'cash'` | `[]` |
| `direction` | `typing.Literal['gainers', 'losers', 'both']` | `'gainers'` | `[]` |
| `min_turnover` | `<class 'float'>` | `0` | `[Ge(ge=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `max_turnover` | `float \| None` | `None` | `[Ge(ge=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `min_change` | `<class 'float'>` | `0` | `[_PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `max_change` | `float \| None` | `None` | `[_PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `top_n` | `int \| None` | `None` | `[Strict(strict=True), Gt(gt=0)]` |

### PreopenRequest

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `csv_text` | `<class 'str'>` | `REQUIRED` | `[MinLen(min_length=1), MaxLen(max_length=2000000)]` |
| `filename` | `<class 'str'>` | `'NSE pre-open.csv'` | `[MaxLen(max_length=255)]` |
| `settings` | `<class 'app.preopen.PreopenSettings'>` | `factory: PreopenSettings` | `[]` |

### AlgoSettings

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `mode` | `typing.Literal['paper', 'live']` | `'paper'` | `[]` |
| `first_direction` | `typing.Literal['setup', 'long', 'short']` | `'setup'` | `[]` |
| `sizing` | `typing.Literal['quantity', 'capital']` | `'capital'` | `[]` |
| `quantity` | `<class 'int'>` | `1` | `[Ge(ge=1), Le(le=100000)]` |
| `capital` | `<class 'float'>` | `10000` | `[Gt(gt=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `target_pct` | `<class 'float'>` | `4` | `[Gt(gt=0), Le(le=100), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `stop_pct` | `<class 'float'>` | `1` | `[Gt(gt=0), Lt(lt=100), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `trailing` | `<class 'bool'>` | `False` | `[]` |
| `trailing_pct` | `<class 'float'>` | `1` | `[Gt(gt=0), Lt(lt=100), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `ladder` | `<class 'bool'>` | `False` | `[]` |
| `pyramiding` | `<class 'bool'>` | `False` | `[]` |
| `max_adds` | `<class 'int'>` | `2` | `[Ge(ge=0), Le(le=20)]` |
| `reference` | `typing.Literal['average', 'original']` | `'original'` | `[]` |
| `reversal_size` | `typing.Literal['initial', 'accumulated']` | `'initial'` | `[]` |
| `max_reversals` | `<class 'int'>` | `20` | `[Ge(ge=0), Le(le=100)]` |
| `max_loss` | `<class 'float'>` | `10000` | `[Gt(gt=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `square_off` | `<class 'str'>` | `'15:15'` | `[]` |
| `slippage_bps` | `<class 'float'>` | `5` | `[Ge(ge=0), Le(le=100), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `fee_per_order` | `<class 'float'>` | `0` | `[Ge(ge=0), _PydanticGeneralMetadata(allow_inf_nan=False)]` |
| `order_timeout_seconds` | `<class 'int'>` | `15` | `[Ge(ge=5), Le(le=60)]` |
| `max_quote_age_seconds` | `<class 'int'>` | `5` | `[Ge(ge=1), Le(le=30)]` |

### AlgoStart

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `symbol` | `<class 'str'>` | `REQUIRED` | `[]` |
| `setup` | `typing.Literal['possible', 'redwala']` | `REQUIRED` | `[]` |
| `settings` | `<class 'app.algo_strategy.AlgoSettings'>` | `factory: AlgoSettings` | `[]` |

### AlgoBacktest

| Field | Python type | Default | Validation metadata |
|---|---|---|---|
| `symbol` | `<class 'str'>` | `REQUIRED` | `[]` |
| `setup` | `typing.Literal['possible', 'redwala']` | `REQUIRED` | `[]` |
| `settings` | `<class 'app.algo_strategy.AlgoSettings'>` | `factory: AlgoSettings` | `[]` |
| `target_date` | `<class 'datetime.date'>` | `REQUIRED` | `[]` |
| `start_time` | `<class 'str'>` | `'09:16'` | `[]` |

## Python definitions by file

Public and internal functions are listed to make the implementation navigable. Names alone are not a substitute for the behavioral specification.

### app/__init__.py


### app/algo_broker.py

Dhan SDK adapter. Order submissions are deliberately never retried here.

- `payload(response)` — line 13.
- `integer(value)` — line 19.
- `trading_response(response, parse)` — line 26.
- Class `OrderSocket` — line 34.
  - `__init__(self, client_id, token, notify)` — line 36.
  - `run(self)` — line 42.
- Class `DhanAlgoBroker` — line 71.
  - `__init__(self, engine, wake)` — line 72.
  - `identity_ok(self)` — line 91.
  - `call(self, method, *args, **kwargs)` — line 95.
  - `connect_orders(self)` — line 104.
  - `close(self)` — line 109.
  - `connect_market(self, ids, on_tick, max_age=5)` — line 116.
  - `_quote_fallback(self)` — line 127.
  - `market_quotes(self)` — line 146.
  - `positions(self)` — line 149.
  - `orders(self)` — line 155.
  - `order(self, intent)` — line 161.
  - `trades(self, order_id)` — line 170.
  - `submit(self, security_id, intent)` — line 178.
  - `cancel(self, order_id)` — line 186.
  - `quotes(self, security_ids, now, max_age=5)` — line 189.
- `position_qty(rows, security_id)` — line 234.
- `same_instrument(row, security_id)` — line 239.

### app/algo_feed.py

Selected-stock Dhan Full feed. No orders or disk I/O on the receive thread.

- `fresh(quote, now, max_age=5, *, depth=False)` — line 13.
- Class `AlgoMarketFeed` — line 28.
  - `__init__(self, client_id, token, notify, on_tick)` — line 29.
  - `subscribe(self, ids)` — line 41.
  - `quotes(self)` — line 46.
  - `accept(self, sid, quote)` — line 50.
  - `receive(self, data, now=None)` — line 65.
  - `run(self)` — line 102.

### app/algo_journal.py

Durable intent/state journal and one-process execution ownership.

- Class `Journal` — line 10.
  - `__init__(self, path)` — line 11.
  - `connect(self)` — line 23.
  - `acquire(self)` — line 32.
  - `release(self)` — line 54.
  - `load(self)` — line 60.
  - `save(self, record, event=None)` — line 64.
  - `settings(self, value=None)` — line 72.

### app/algo_service.py

Selected-stock paper/live controller, isolated from scanner lifecycle.

- Class `AlgoService` — line 18.
  - `__init__(self, engine)` — line 19.
  - `now(self)` — line 36.
  - `save_settings(self, settings)` — line 39.
  - `snapshot(self)` — line 43.
  - `_generation(record)` — line 53.
  - `on_tick(self, security_id, quote)` — line 58.
  - `_observed(self, record, strategy)` — line 109.
  - `_save(self, record, event=None)` — line 134.
  - `_launch(self)` — line 143.
  - `start(self, request)` — line 151.
  - `command(self, session_id, action)` — line 192.
  - `_get_broker(self)` — line 211.
  - `_position_check(self, record, strategy, broker)` — line 218.
  - `_preflight(self, record, strategy, broker)` — line 225.
  - `_submit(self, record, strategy, action, broker, quote)` — line 237.
  - `_reconcile_order(self, record, strategy, broker, quote)` — line 332.
  - `step(self, record, broker, quote)` — line 438.
  - `_run(self)` — line 527.
  - `shutdown(self)` — line 563.
  - `backtest(self, request)` — line 574.
  - `_backtest(self, request)` — line 585.

### app/algo_strategy.py

Fill-driven ladder strategy shared by paper execution and historical replay.

- Class `AlgoSettings` — line 10.
  - `side_for_setup(self, setup)` — line 34.
  - `check_time(cls, value)` — line 43.
- Class `AlgoStart` — line 50.
- Class `AlgoBacktest` — line 57.
  - `check_start(cls, value)` — line 63.
- Class `Ladder` — line 71.
  - Field `settings: dict`.
  - Field `initial_side: int`.
  - Field `base_qty: int`.
  - Field `net_qty: int` = `0`.
  - Field `average: float` = `0`.
  - Field `original: float` = `0`.
  - Field `best: float` = `0`.
  - Field `stop: float` = `0`.
  - Field `next_add: float` = `0`.
  - Field `adds: int` = `0`.
  - Field `reversals: int` = `0`.
  - Field `realized: float` = `0`.
  - Field `fees: float` = `0`.
  - Field `started: bool` = `False`.
  - Field `done: bool` = `False`.
  - Field `day_locked: bool` = `False`.
  - Field `last_reason: str` = `''`.
  - Field `fills: list` = `field(default_factory=list)`.
  - `config(self)` — line 92.
  - `side(self)` — line 96.
  - `mark(self, price)` — line 99.
  - `levels(self)` — line 102.
  - `update_risk(self, price)` — line 110.
  - `fill(self, signed_qty, price, stamp, fill_id)` — line 121.
  - `action(self, price, cutoff=False, entry_price=None, *, allow_reversal=True)` — line 149.
  - `completed(self, intent)` — line 181.
- `paper_execute(strategy, action, bid, ask, stamp)` — line 203.
- `replay_path(bar, side)` — line 210.
- `replay(candles, settings, initial_side)` — line 225.

### app/circuit_bands.py

Conservative classification of today's fixed cash-equity circuit limits.

- `number(value)` — line 6.
- `reference_close(quote, daily, session)` — line 14.
- `classify(upper, lower, reference, *, fresh, is_fno=False, inconsistent=False)` — line 29.

### app/daily_filter.py

- `_daily_price(values: list, index: int)` — line 9.
- `parse_daily_sessions(data: dict, target_date: date)` — line 17.
- `calculate_daily_filter(data: dict, target_date: date, volume_limit: float=4.0, resistance_capacity: int=0)` — line 55.
- `apply_daily_volume_limit(daily: dict | None, volume_limit: float)` — line 100.

### app/dhan_scanner.py

- `parse_symbols(raw: str)` — line 49.
- `_float_or_none(value: Any)` — line 60.
- `_int_or_none(value: Any)` — line 70.
- `_extract_data(response: Any)` — line 77.
- `_format_dhan_error(remarks: Any)` — line 90.
- `_should_stop_api_batch(error: Exception | str)` — line 103.
- Class `Instrument` — line 112.
  - Field `symbol: str`.
  - Field `security_id: str`.
  - Field `name: str`.
  - Field `exchange_segment: str` = `'NSE_EQ'`.
  - Field `instrument_type: str` = `'EQUITY'`.
- Class `Candle` — line 121.
  - Field `start: datetime`.
  - Field `open: float`.
  - Field `high: float`.
  - Field `low: float`.
  - Field `close: float`.
  - Field `volume: int` = `0`.
  - `end(self)` — line 130.
  - `turnover(self)` — line 134.
  - `color(self)` — line 138.
  - `update(self, price: float, volume_delta: int)` — line 145.
- Class `OpeningSignal` — line 153.
  - Field `first_label: str`.
  - Field `first: Candle`.
  - Field `second_label: str`.
  - Field `second: Candle | None`.
  - Field `volume_average: float | None`.
  - Field `volume_multiplier: float | None`.
  - Field `colors_match: bool`.
  - Field `possible_candidate: bool`.
  - Field `reason: str`.
- Class `StockState` — line 166.
  - Field `instrument: Instrument`.
  - Field `previous_close: float | None` = `None`.
  - Field `ltp: float | None` = `None`.
  - Field `percent_change: float | None` = `None`.
  - Field `day_volume: int | None` = `None`.
  - Field `last_cumulative_volume: int | None` = `None`.
  - Field `current_candle: Candle | None` = `None`.
  - Field `completed_candle: Candle | None` = `None`.
  - Field `last_tick_time: datetime | None` = `None`.
  - Field `last_tick_received_at: datetime | None` = `None`.
  - Field `opening_volume_average: float | None` = `None`.
  - Field `opening_volume_samples: list[dict[str, Any]]` = `field(default_factory=list)`.
  - Field `opening_candles: list[Candle]` = `field(default_factory=list)`.
  - Field `today_opening_volume: int | None` = `None`.
  - Field `volume_multiplier: float | None` = `None`.
  - Field `opening_colors_match: bool` = `False`.
  - Field `possible_candidate: bool` = `False`.
  - Field `resistance_context: dict` = `field(default_factory=dict)`.
  - Field `ltp_updated_at: datetime | None` = `None`.
  - Field `redwala_gira: bool` = `False`.
  - Field `qualifies_scan: bool` = `False`.
  - Field `daily_filter: dict[str, Any] | None` = `None`.
  - Field `signal_session: date | None` = `None`.
  - Field `opening_pair_confirmed: bool` = `False`.
  - Field `confirmed_opening_candle: Candle | None` = `None`.
  - Field `confirmed_session_candles: dict[datetime, Candle]` = `field(default_factory=dict)`.
  - Field `post_opening_trough: float | None` = `None`.
  - Field `post_opening_trough_session: date | None` = `None`.
  - Field `post_opening_peak: float | None` = `None`.
  - Field `post_opening_peak_session: date | None` = `None`.
  - Field `retest_break: bool` = `False`.
  - Field `retest_break_at: str | None` = `None`.
  - Field `retest_status: str` = `'waiting'`.
  - Field `retest_reason: str | None` = `None`.
  - Field `retest_attempt_at: datetime | None` = `None`.
  - Field `retest_checked_through: datetime | None` = `None`.
  - Field `volume_session: date | None` = `None`.
  - Field `preparation_status: str` = `'unresolved'`.
  - Field `confirmation_status: str` = `'pending'`.
  - Field `confirmation_retry_at: float` = `0.0`.
  - Field `confirmation_attempts: int` = `0`.
  - Field `opening_metadata_pending: bool` = `False`.
  - Field `provisional_setup: str | None` = `None`.
  - Field `feed_baseline_session: date | None` = `None`.
  - Field `feed_incomplete: bool` = `True`.
  - Field `opening_first_tick: datetime | None` = `None`.
  - Field `opening_last_tick: datetime | None` = `None`.
  - Field `opening_boundary_seen: bool` = `False`.
  - Field `feed_baseline_volume: int | None` = `None`.
  - Field `opening_boundary_volume: int | None` = `None`.
  - Field `upper_circuit_limit: float | None` = `None`.
  - Field `lower_circuit_limit: float | None` = `None`.
  - Field `circuit_fetched_at: datetime | None` = `None`.
  - Field `circuit_attempt_at: datetime | None` = `None`.
  - Field `circuit_error: str | None` = `None`.
  - Field `circuit_reference_close: float | None` = `None`.
  - Field `candidate_reason: str | None` = `None`.
  - Field `status: str` = `'waiting'`.
  - Field `error: str | None` = `None`.
- Class `InstrumentResolver` — line 228.
  - `__init__(self, csv_path: Path=SCRIP_MASTER_PATH, index_path: Path | None=None)` — line 229.
  - `ensure_master(self, max_age_hours: int=24)` — line 233.
  - `resolve(self, symbols: list[str])` — line 246.
  - `_load_index(self)` — line 263.
  - `_index_is_fresh(self)` — line 295.
- Class `ScannerEngine` — line 301.
  - `__init__(self, store: ConfigStore)` — line 302.
  - `algo(self)` — line 340.
  - `load_saved(self)` — line 347.
  - `prepare_symbols(self, symbols: list[str])` — line 360.
  - `volume_filters(self)` — line 401.
  - `update_volume_filters(self, settings: VolumeFilterSettings)` — line 404.
  - `_refresh_filter_subscriptions(self, feed: Any, stop_event: threading.Event, refresh_event: threading.Event)` — line 453.
  - `credentials_ready(self)` — line 480.
  - `_client(self)` — line 484.
  - `cache_previous_closes(self)` — line 492.
  - `_daily_ready(self, state: StockState, session: date)` — line 558.
  - `_five_day_close_level(daily: dict | None, session: date)` — line 564.
  - `_volume_ready(state: StockState, session: date)` — line 578.
  - `_cache_entry(self, state: StockState)` — line 582.
  - `_prepare_daily(self, client: Any, state: StockState, session: date, *, need_five: bool=False)` — line 588.
  - `_mark_resistance_pending(self, state: StockState, session: date)` — line 649.
  - `_prepare_volume(self, client: Any, state: StockState, session: date, stop_event: threading.Event | None=None)` — line 660.
  - `cache_opening_volume_averages(self)` — line 681.
  - `_work_lock(self, symbol: str)` — line 685.
  - `_cache_batch(self)` — line 690.
  - `_persist_cache(self, state: StockState)` — line 704.
  - `_prepare_scan_universe(self)` — line 716.
  - `_fetch_opening_volume_history(self, client: Any, instrument: Instrument)` — line 783.
  - `_select_historical_opening_samples(self, candles: list[Candle], before_date: date, count: int)` — line 845.
  - `_first_opening_candle(candles: list[Candle])` — line 880.
  - `_looks_like_opening_circuit(candle: Candle, previous_close: float | None)` — line 885.
  - `_instrument_cache_key(instrument: Instrument)` — line 896.
  - `_daily_payload(bars: list[dict])` — line 900.
  - `_fetch_daily_filter(self, client: Any, instrument: Instrument, target_date: date)` — line 904.
  - `_qualify_signal(self, signal: OpeningSignal, daily_filter: dict | None, session: date)` — line 957.
  - `_previous_day_crosses(first: Candle | None, daily_filter: dict | None, session: date | None, possible: bool, redwala: bool)` — line 1026.
  - `_second_candle_pdl_cross(first: Candle | None, candles: list[Candle], daily: dict | None, session: date | None, redwala: bool)` — line 1037.
  - `backtest_date(self, target_date: date, scan_type: str='opening', *, volume_filters: VolumeFilterSettings | None=None)` — line 1046.
  - `_backtest_date(self, target_date: date, scan_type: str='opening')` — line 1059.
  - `_fetch_backtest_history(self, client: Any, instrument: Instrument, target_date: date)` — line 1146.
  - `_build_backtest_row(self, instrument: Instrument, target_date: date, candles: list[Candle], daily_filter: dict[str, Any] | None=None)` — line 1172.
  - `_backtest_error_row(instrument: Instrument, target_date: date, error: str)` — line 1249.
  - `_priority_history(self)` — line 1276.
  - `evaluate_opening_candidates(self, client: Any | None=None, *, only_pending: bool=False)` — line 1290.
  - `_confirm_opening_candidates(self, client: Any | None=None, *, only_pending: bool=False)` — line 1294.
  - `_screen_live_opening(self, session: date, states: list[StockState] | None=None)` — line 1377.
  - `_live_opening_complete(self, state: StockState, session: date)` — line 1412.
  - `refresh_circuit_limits(self, client: Any | None=None)` — line 1421.
  - `_quote_call(self, method: Any, securities: dict[str, list[int]])` — line 1484.
  - `_refresh_circuit_limits_loop(self, stop_event: threading.Event)` — line 1493.
  - `_apply_opening_candidate(self, symbol: str, candles: list[Candle])` — line 1501.
  - `_update_live_resistance(self, state: StockState)` — line 1543.
  - `_live_resistance_fields(self, state: StockState)` — line 1557.
  - `_retest_result(self, first: Candle, candles: list[Candle], daily: dict | None, qualification: dict)` — line 1575.
  - `_merge_confirmed_session(state: StockState, candles: list[Candle])` — line 1592.
  - `_update_retest(self, state: StockState)` — line 1600.
  - `evaluate_retest_breaks(self, stop_event: threading.Event | None=None)` — line 1617.
  - `_refresh_retest_breaks(self, stop_event: threading.Event)` — line 1688.
  - `_calculate_opening_signal(self, candles: list[Candle], volume_average: float | None)` — line 1700.
  - `_fetch_opening_candles(self, client: Any, instrument: Instrument)` — line 1732.
  - `_evaluate_first_opening_candle(self, candles: list[Candle])` — line 1764.
  - `_opening_window_candles(candles: list[Candle])` — line 1772.
  - `_merge_opening_candles(self, state: StockState, candles: list[Candle])` — line 1798.
  - `_parse_intraday_candles(self, response: Any)` — line 1812.
  - `_cache_from_ohlc_batch(self, client: Any, states: list[StockState])` — line 1847.
  - `_ohlc_batch_with_retry(self, client: Any, securities: dict[str, list[int]])` — line 1880.
  - `_historical_daily_with_retry(self, client: Any, *args: Any)` — line 1894.
  - `_intraday_with_retry(self, client: Any, *args: Any)` — line 1915.
  - `_history_call(self, method: Any, *args: Any, **kwargs: Any)` — line 1929.
  - `_history_reserved(self)` — line 1962.
  - `start(self)` — line 1966.
  - `stop(self)` — line 2055.
  - `_opening_check_complete(self, state: StockState, session: date)` — line 2073.
  - `_refresh_opening_candidates_when_ready(self, stop_event: threading.Event, refresh_event: threading.Event)` — line 2085.
  - `_run_opening_confirmation(self, stop_event: threading.Event)` — line 2109.
  - `repair_missing_candles(self)` — line 2137.
  - `_repair_symbol(self, client: Any, instrument: Instrument, start: datetime, end: datetime)` — line 2164.
  - `_on_connect(self, _feed: Any)` — line 2190.
  - `_on_close(self, _feed: Any)` — line 2199.
  - `_on_error(self, _feed: Any, error: Exception)` — line 2208.
  - `_invalidate_opening_feed(self)` — line 2216.
  - `_on_message(self, _feed: Any, data: Any)` — line 2223.
  - `_tick_time(self, ltt: Any)` — line 2329.
  - `snapshot(self)` — line 2344.
  - `_redwala_breaks(first: Candle | None, candles: list[Candle], daily: dict | None, eligible: bool, trough: float | None=None)` — line 2366.
  - `_row(self, state: StockState)` — line 2381.
  - `_circuit_fields(state: StockState)` — line 2463.

### app/feed_lifecycle.py

Bounded shutdown for the scanner's SDK feed (separate from algo feeds).

- `close_market_feed(feed, timeout=1.0)` — line 10.

### app/fno_symbols.py


### app/history_cache.py

Small transactional cache updates, independent of credentials/settings JSON.

- Class `HistoryCache` — line 10.
  - `__init__(self, path: Path)` — line 11.
  - `connection(self)` — line 17.
  - `update(self, entries=None, closes=None, *, legacy=False)` — line 38.
  - `load(self)` — line 57.
  - `get(self, kind, instrument)` — line 65.
  - `put(self, kind, instrument, value)` — line 70.

### app/main.py

- `lifespan(_app: FastAPI)` — line 35.
- `prevent_cached_api_state(request, call_next)` — line 47.
- `dashboard()` — line 57.
- `get_config()` — line 69.
- `save_volume_filters(payload: VolumeFilterSettings)` — line 82.
- `save_credentials(payload: CredentialsIn)` — line 87.
- `save_symbols(payload: SymbolsIn)` — line 96.
- `get_preopen_import()` — line 114.
- `preview_preopen(payload: PreopenRequest)` — line 119.
- `apply_preopen(payload: PreopenRequest)` — line 127.
- `cache_data()` — line 144.
- `cache_volume_average()` — line 153.
- `run_backtest(payload: BacktestIn)` — line 165.
- `start_scan()` — line 179.
- `stop_scan()` — line 188.
- `repair_missing()` — line 194.
- `get_state()` — line 210.
- `save_algo_settings(payload: AlgoSettings)` — line 215.
- `start_algo(payload: AlgoStart)` — line 221.
- `exit_algo(session_id: str)` — line 230.
- `resume_algo(session_id: str)` — line 239.
- `backtest_algo(payload: AlgoBacktest)` — line 248.

### app/opening_filters.py

Optional daily-history checks for Candidates and Retest Break; not Redwala.

- `_samples(daily: dict | None, session: date, key: str, count: int, *, need_open: bool=False)` — line 8.
- `missing_history(daily: dict | None, session: date, settings: VolumeFilterSettings)` — line 29.
- `evaluate(daily: dict | None, session: date, opening: float | None, settings: VolumeFilterSettings)` — line 38.

### app/opening_patterns.py

Opening-candle patterns evaluated from completed, dated minute candles.

- `later_candles(first, candles)` — line 5.
- `first_high_broken(first, candles)` — line 12.
- `retest_sequence(first, candles)` — line 16.

### app/preopen.py

NSE pre-open universe selection from the supplied cash/F&O scripts.

- Class `PreopenSettings` — line 14.
  - `check_ranges(self)` — line 25.
- Class `PreopenRequest` — line 39.
- `numeric(value: str | None)` — line 45.
- `filter_csv(payload: PreopenRequest)` — line 55.

### app/resistance.py

Session-bound daily swing resistance. No intraday/future candles select a level.

- `history_days(settings: VolumeFilterSettings)` — line 10.
- `missing_history(daily: dict | None, session: date, settings: VolumeFilterSettings)` — line 14.
- `_select(rows: tuple, lookback: int, left: int, right: int, min_age: int, max_age: int, pullback_enabled: bool, pullback_min: float)` — line 36.
- `selection(daily: dict | None, session: date, settings: VolumeFilterSettings)` — line 59.
- `above(price: float | None, selected: dict)` — line 79.
- `replay_badges(candles, first, selected: dict)` — line 85.

### app/schemas.py

- Class `VolumeFilterSettings` — line 9.
  - `resistance_ranges(self)` — line 36.
- Class `CredentialsIn` — line 44.
- Class `SymbolsIn` — line 50.
- Class `BacktestIn` — line 54.
- Class `MessageOut` — line 60.
- Class `ConfigOut` — line 65.
- Class `DailyVolumeFilter` — line 74.
- Class `QualificationFields` — line 95.
- Class `StockRow` — line 126.
- Class `StateOut` — line 175.
- Class `BacktestRow` — line 186.
- Class `BacktestOut` — line 209.

### app/setup_price_filters.py

Optional price filters with explicit setup scope and session-bound cached inputs.

- `missing_history(daily: dict | None, session: date, settings: VolumeFilterSettings, setup: str)` — line 8.
- `evaluate(daily: dict | None, session: date, opening: float, close: float, settings: VolumeFilterSettings, setup: str)` — line 34.

### app/storage.py

- Class `AppConfig` — line 18.
  - Field `volume_filters: VolumeFilterSettings` = `field(default_factory=VolumeFilterSettings)`.
  - Field `client_id: str` = `''`.
  - Field `access_token: str` = `''`.
  - Field `symbols: list[str]` = `field(default_factory=list)`.
  - Field `previous_closes: dict[str, float]` = `field(default_factory=dict)`.
  - Field `opening_volume_cache: dict[str, dict[str, Any]]` = `field(default_factory=dict)`.
- Class `ConfigStore` — line 27.
  - `__init__(self, path: Path=CONFIG_PATH)` — line 28.
  - `load(self, *, include_cache: bool=True)` — line 34.
  - `save(self, config: AppConfig)` — line 61.
  - `_save_settings(self, payload: dict)` — line 73.
  - `update_credentials(self, client_id: str, access_token: str)` — line 78.
  - `update_volume_filters(self, settings: VolumeFilterSettings)` — line 93.
  - `update_symbols(self, symbols: list[str])` — line 100.
  - `load_preopen_import(self)` — line 107.
  - `save_preopen_import(self, payload: dict)` — line 112.
  - `update_previous_closes(self, previous_closes: dict[str, float])` — line 119.
  - `update_opening_volume_cache(self, entries: dict[str, dict[str, Any]])` — line 124.

### scripts/launch_app.py

Double-click entry point: reuse a running app or run one foreground server.

- `app_ready(url=URL)` — line 18.
- `open_dashboard(url=URL)` — line 30.
- `open_when_ready(stopped, url=URL)` — line 39.
- `main()` — line 52.

## Browser function and control inventory

### app/static/app.js

- `fmtNumber(value, digits = 2)` — line 78.
- `filterDescription(settings = {})` — line 86.
- `additionalOpeningDescription(settings = {})` — line 90.
- `resistanceDescription(s = {})` — line 97.
- `turnoverDescription(settings = {})` — line 103.
- `fmtInt(value)` — line 107.
- `fmtTurnover(value)` — line 112.
- `fmtTime(value)` — line 120.
- `escapeHtml(value)` — line 133.
- `fmtCandle(row)` — line 143.
- `fmtDateInput(date, offsetDays = 0)` — line 150.
- `fmtBacktestCandle(start, color)` — line 158.
- `fmtOpeningPair(row)` — line 164.
- `fmtOpeningTimeline(row)` — line 174.
- `setMessage(text, isError = false)` — line 200.
- `fmtDailyFilter(row)` — line 205.
- `hasSmallOpeningGap(row)` — line 215.
- `fmtSignalBadge(row, reason)` — line 224.
- `fmtCircuitDistance(row, side)` — line 243.
- `api(path, options = {}, timeoutMs = 0)` — line 254.
- `setBusy(button, busy)` — line 281.
- `runAction(button, fn)` — line 285.
- `restoreDashboardVolumeFilter()` — line 303.
- `matchesDashboardVolume(row, backtest = false)` — line 314.
- `applyDashboardVolumeFilter()` — line 319.
- `matchesDashboardPrice(row, backtest = false)` — line 354.
- `applyDashboardPriceFilter()` — line 359.
- `displayFilterDescription(backtest = false)` — line 378.
- `matchesDashboardCircuit(row)` — line 392.
- `matchesSetup(row)` — line 402.
- `dashboardPriority(row)` — line 411.
- `compareLiveStocks(a, b)` — line 418.
- `renderState(state)` — line 426.
- `setActiveView(view)` — line 530.
- `renderBacktest(result)` — line 541.
- `backtestOpeningPrices(row)` — line 610.
- `updateBacktestFiltersStatus()` — line 617.
- `runBacktest()` — line 630.
- `renderCredentialsStatus()` — line 680.
- `refreshConfig()` — line 690.
- `normalizedFilterSettings(settings = {})` — line 737.
- `readFilterSettings()` — line 751.
- `updateFilterChangesStatus()` — line 797.
- `filterFormChanged(event)` — line 809.
- `refreshState()` — line 817.
- `saveFilterSettings(settings)` — line 825.
- `algoBacktestPayload()` — line 956.
- `updateAlgoBacktestStale()` — line 961.
- `readAlgoSettings()` — line 980.
- `algoRowButton(row, backtest)` — line 995.
- `algoFirstSide(settings, setup)` — line 1001.
- `algoFills(fills)` — line 1005.
- `renderAlgo(data)` — line 1008.
- `handleAlgoClick(event)` — line 1038.

Browser preference identifiers: `scanner.dashboardCircuit.v1`, `scanner.dashboardPrice.v1`, `scanner.dashboardVolume.v1`.

### app/static/preopen.js

- `settings()` — line 13.
- `invalidate()` — line 19.
- `show(result)` — line 26.
- `runPreview()` — line 37.

### HTML controls

| Element | ID | Input type |
|---|---|---|
| form | `credentialsForm` | — |
| input | `clientId` | — |
| input | `accessToken` | password |
| form | `symbolsForm` | — |
| textarea | `symbolsText` | — |
| button | `cacheButton` | button |
| button | `volumeCacheButton` | button |
| button | `startButton` | button |
| button | `stopButton` | button |
| button | `repairButton` | button |
| form | `preopenForm` | — |
| input | `preopenFile` | file |
| input | `preopenCash` | radio |
| input | `preopenFno` | radio |
| select | `preopenDirection` | — |
| input | `preopenMinTurnover` | number |
| input | `preopenMaxTurnover` | number |
| input | `preopenMinChange` | number |
| input | `preopenMaxChange` | number |
| input | `preopenTopN` | number |
| button | `preopenPreview` | submit |
| button | `preopenApply` | button |
| form | `volumeFiltersForm` | — |
| input | `dailyVolumeMax` | number |
| input | `minuteVolumeMin` | number |
| input | `firstCandleTurnoverMin` | number |
| button | `saveVolumeFilters` | submit |
| input | `todayOpenCross` | checkbox |
| input | `monthlyFilter` | checkbox |
| input | `lastTwoDaysFilter` | checkbox |
| input | `redwalaOpenPreviousClose` | checkbox |
| input | `redwalaOpenGapMax` | number |
| input | `redwalaOpenTolerance` | checkbox |
| input | `redwalaOpenToleranceMax` | number |
| input | `pdhlFilter` | checkbox |
| input | `pdhlMax` | number |
| input | `possibleOpenPreClose` | checkbox |
| input | `possibleOpenPreCloseMax` | number |
| input | `resistanceFilter` | checkbox |
| input | `resistanceLookback` | number |
| input | `resistanceLeft` | number |
| input | `resistanceRight` | number |
| input | `resistanceMinAge` | number |
| input | `resistanceMaxAge` | number |
| input | `resistanceBuffer` | number |
| input | `resistancePullback` | checkbox |
| input | `resistancePullbackMin` | number |
| button | `liveTab` | button |
| button | `backtestTab` | button |
| select | `setupFilter` | — |
| input | `dashboardVolumeEnabled` | checkbox |
| input | `dashboardVolumeMin` | number |
| input | `dashboardPriceEnabled` | checkbox |
| input | `dashboardPriceMax` | number |
| input | `dashboardCircuitEnabled` | checkbox |
| input | `backtestDate` | date |
| button | `backtestButton` | button |
| form | `algoSettingsForm` | — |
| select | `algoMode` | — |
| select | `algoFirstDirection` | — |
| input | `algoCapital` | number |
| input | `algoTarget` | number |
| input | `algoStop` | number |
| input | `algoTrailing` | checkbox |
| input | `algoTrailPct` | number |
| input | `algoLadder` | checkbox |
| input | `algoPyramid` | checkbox |
| input | `algoMaxAdds` | number |
| input | `algoMaxReversals` | number |
| input | `algoMaxLoss` | number |
| input | `algoSquareOff` | time |
| input | `algoSlippage` | number |
| input | `algoFee` | number |
| button | `algoSave` | submit |
| form | `algoBacktestForm` | — |
| input | `algoBacktestSymbol` | — |
| select | `algoBacktestSetup` | — |
| input | `algoBacktestDate` | date |
| input | `algoBacktestTime` | time |
| button | `algoBacktestRun` | submit |
