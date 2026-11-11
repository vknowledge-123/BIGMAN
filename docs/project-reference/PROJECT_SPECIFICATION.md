# Dhan Turnover Scanner — detailed project and rebuild specification

Documentation date: **11 November 2026**, India Standard Time. This describes the source files in the main project at the time of inspection, including its uncommitted changes. It is an implementation specification, not a claim that every scenario has been tested against a live broker.

Read this file first when rebuilding the application. The accompanying `INTERFACES_AND_SOURCE_MAP.md`, `MODEL_SCHEMAS.json`, `DEFAULT_SETTINGS.json`, `TEST_INVENTORY.md`, and `SOURCE_MANIFEST.json` provide exact structural details. `AI_REBUILD_PROMPT.md` supplies a reusable instruction for another AI tool. No actual credentials, uploaded customer CSVs, caches, positions, orders or account records are included.

## Admin-hosted accounts update

The application now includes email/password/TOTP authentication for administrators and members, signup with mandatory admin approval, read-only member dashboards, server-side role and CSRF enforcement, and shared display preferences. See [MEMBER_HOSTING.md](MEMBER_HOSTING.md) for the complete account, API-security, data-storage, setup, hosting and recovery specification. These requirements are part of any rebuild. Dhan subscriptions and trading stay in one administrator-hosted process. Members cannot invoke scanner controls, change filters, inspect credentials, run backtests or trade.

## HTTP security update

Implement [SECURITY.md](SECURITY.md) as part of the rebuild: bounded HTTP input processing, layered request/password/OTP budgets, output escaping and browser security headers, protected OpenAPI, generic unexpected errors and input-free validation errors. The dependency pins in requirements.txt supersede earlier version examples in this report. The public launcher health probe is /health; /openapi.json requires an active administrator. Public Swagger/ReDoc pages are disabled.

## Contents

1. Product scope and implementation status
2. Architecture and component responsibilities
3. Installation, launch and deployment
4. Instruments, credentials and stock selection
5. Market data, dates, candles and arithmetic
6. Scanner setup qualification
7. Optional daily and opening filters
8. Daily resistance algorithm
9. Badge rules and sorting
10. Dashboard and browser behavior
11. Preparation, live confirmation and request scheduling
12. Storage and cache contracts
13. Scanner backtesting
14. Selected-stock algo trading
15. Order handling and reconciliation
16. Algo historical replay and P&L
17. API and data contracts
18. Error handling and troubleshooting
19. Verification and acceptance requirements
20. Rebuild sequence and known boundaries
21. Verified circuit-band display filter

## 1. Product scope and implementation status

The application is a locally hosted NSE equity scanner with a browser dashboard, Dhan market-data integration, historical setup backtesting, and manually selected stock algo execution in paper or real-order mode. Its main purpose is to prepare historical inputs before the market opens, recognize first-minute setups quickly after 09:16 IST, and keep monitoring later breakout badges.

It is a single-account, single-server application. It is not a hosted multi-user trading platform. The browser talks to a local FastAPI server. The server connects to Dhan and owns market subscriptions, calculations, historical caches, and execution state. The browser does not receive the saved access token.

### Implemented features in the inspected main source

| Area | Functionality |
|---|---|
| Credentials | Save client ID/token locally; retain a saved token across browser refreshes |
| Universe | Manual symbol list, Dhan security-ID resolution, NSE pre-open CSV preview/filter/apply, Cash/F&O classification |
| Preparation | Previous close/high/low, daily relative volume, first-minute historical volume average, optional opening-history and resistance inputs |
| Live setups | Possible Candidate, Redwala Gira, Retest Break, provisional versus confirmed states |
| Filters | Configurable daily/minute volume and turnover, five-session opening cross, twenty-session close filter, last-two-days condition, setup-specific price filters, daily resistance |
| Display | Setup selector, absolute first-minute volume, maximum stock price, verified circuit band >=20%, badges, priority grouping, turnover sorting, first five candle cards, UC/LC distances |
| Historical scan | Date-relative setup qualification, data errors/warnings, badges and historical price/volume display filters |
| Execution | Selected-stock paper/live ladder, direction override, capital sizing, stops/targets/trailing, pyramiding, reversals, loss limits, square-off |
| Order integrity | Intent journal, order socket notifications, REST trade/position reconciliation, partial-fill handling, duplicate prevention and restart pause |
| Algo replay | One-stock OHLC backtest, explicit initial-minute and reversal rules, slippage, fees, gross/net P&L |
| Operations | Windows double-click launcher, local browser UI, single-process journal ownership, automated test suites |

### Not implemented or intentionally removed

- **Afternoon scan:** retired; do not recreate its buttons, routes or scheduling.
- **Standalone Premarket Setup:** retired. NSE pre-open CSV selection and premarket historical caching remain implemented; these are different features.
- **US stock scanning/trading:** not implemented. Instrument and order paths target `NSE_EQ` / `EQUITY`.
- **RSI, 55 EMA, Fourier, Laplace, Z-transform filters:** discussed historically but not implemented requirements in the inspected application.
- No automatic order entry for every scan match. A user selects a stock using Start Algo.
- No broker-hosted stop-loss or target bracket is installed by this strategy. Exits are application-managed.

## 2. Architecture and component responsibilities

```text
Browser: index.html + styles.css + app.js + preopen.js
    | JSON HTTP: config, actions, state polling, backtests
FastAPI: app/main.py
    |-- ConfigStore --> config.json and config-preopen.json
    |-- ScannerEngine --> Dhan SDK Quote feed + history/quote REST
    |       |-- daily_filter / opening_filters / setup_price_filters
    |       |-- opening_patterns / resistance
    |       `-- HistoryCache --> config-cache.sqlite3
    `-- AlgoService --> Ladder strategy + execution worker
            |-- DhanAlgoBroker --> order/position/trade REST
            |-- AlgoMarketFeed --> separate Full market websocket
            |-- OrderSocket --> order notifications
            `-- Journal --> algo.sqlite3 + exclusive process lock
```

| File | Responsibility |
|---|---|
| `app/main.py` | HTTP routing, request/response validation, application lifespan, static asset versioning |
| `app/schemas.py` | Scanner settings, credentials/symbol input, live/backtest row and response models |
| `app/dhan_scanner.py` | Resolver, candle model, stock state, preparation, subscriptions, qualification, confirmation, scan replay, rate scheduling and state snapshots |
| `app/daily_filter.py` | Parse dated daily bars, calculate daily ratio and price exception, reevaluate cached ratio thresholds |
| `app/opening_filters.py` | Twenty-session and last-two-session conditions and required-history validation |
| `app/setup_price_filters.py` | Possible Candidate opening gap and PDHL; Redwala previous-close crossing and tolerance |
| `app/resistance.py` | Historical swing selection, memoization, breakout comparisons, replay badges |
| `app/opening_patterns.py` | Later first-high breakout and consecutive-green Retest Break sequence |
| `app/preopen.py` / `app/fno_symbols.py` | CSV parsing/filtering and static equity F&O classification |
| `app/storage.py` / `app/history_cache.py` | Configuration, cache migration, per-stock/session SQLite storage and raw-history reuse |
| `app/feed_lifecycle.py` | Bounded shutdown of the scanner SDK feed |
| `app/algo_strategy.py` | Fill-driven position accounting, risk decisions, paper fills and historical replay |
| `app/algo_service.py` | Selected-stock session lifecycle, tick observations, serialized execution and replay qualification |
| `app/algo_broker.py` | Dhan order/portfolio adapter, quote fallback, order notifications |
| `app/algo_feed.py` | Full-feed binary parsing, timestamps, LTP/depth freshness and reconnect |
| `app/algo_journal.py` | Durable sessions/events/defaults and one-process ownership |
| `app/static/app.js` | Forms, polling, badges, tables, local display filters, execution controls and stale-result notices |
| `app/static/preopen.js` | CSV upload, debounced preview, stale-response protection and apply workflow |
| `scripts/launch_app.py` / `Start Scanner.bat` | Local launch, port ownership, package checks and browser opening |

The frontend is plain JavaScript and HTML/CSS. There is no React build step or required Node runtime for normal application use. Node is used by JavaScript tests. SQLite is provided by Python.

Use one server process for trading. A scanner stop and an algo stop are intentionally different operations. Saving scanner filters does not change the immutable execution settings of a running algo.

## 3. Installation, launch and deployment

The launcher checks for Python **3.10 or newer**. Python 3.11 is the conservative reproduction baseline used for this project; compatibility with every newer release is not asserted. Copy the project source, not another operating system's virtual environment.

Pinned packages in `requirements.txt`:

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
dhanhq==2.2.0
pandas==2.2.3
requests==2.32.3
pydantic==2.10.4
pytest==8.3.4
```

Windows PowerShell, from the extracted project root:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\launch_app.py
```

No PowerShell activation-policy change is necessary when invoking the environment's Python directly. After initial installation, double-click `Start Scanner.bat`.

macOS/Linux equivalent:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/launch_app.py
```

The launcher binds `127.0.0.1:8000`, opens the browser after `/openapi.json` reports the expected application title, and runs a single non-reloading server. It first tries a project `.venv`, then `venv`, then installed Python on Windows. If a healthy scanner already occupies the port, it opens that running instance; it does not replace it. This explains why launching a newly extracted copy can still display an older running version.

For direct non-reloading startup:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`--reload` and the development PowerShell scripts are for development, not real execution. Close/verify active positions before stopping or changing the running application. On restart, unfinished algo sessions pause; restarting the server does not itself flatten positions.

Keep the server window open. Public hosting requires the configured HTTPS origin and a reverse proxy; see MEMBER_HOSTING.md. Both administrators and members require password plus TOTP login. Use a single worker without automatic reload.

When sharing a copy, exclude credentials and all contents of `data/` that identify accounts, customer uploads or trading history. Back up private runtime data separately. Static asset URLs include content hashes, and HTML/API responses disable caching to reduce frontend/backend version mismatch.

## 4. Instruments, credentials and stock selection

### 4.1 Credentials

The configuration stores client ID and access token in local JSON. The token is not encrypted at rest. `/api/config` returns `has_credentials` and the client ID, not the token.

A blank token when saving the same account means retain the existing token. A blank token for a different client ID, or with no saved token, fails validation. The browser shows the saved-credentials state rather than refilling the secret field. Token expiry still requires a fresh token; saving does not renew a broker token.

Changing the active account/token while an algo is running causes identity checks to block continued execution until reconciled. This prevents an existing session from silently moving to another account.

### 4.2 Manual symbols and instrument master

Manual input accepts newline, comma and tab separators; trims and uppercases symbols; removes duplicates while retaining first occurrence order. Empty input cannot replace the list.

The resolver downloads Dhan's scrip master, caches it with a 24-hour freshness target and builds a local NSE equity index. It resolves symbols to security ID, exchange segment, instrument type and display name. Unknown symbols are reported, not silently assigned another instrument. The instrument cache key is `segment:type:security_id`, not just symbol.

Saving/replacing the universe stops the old scanner subscription. Reprepare the new list and Start Live again. Existing algo sessions remain separate. Failed instrument lookup should preserve the existing universe.

### 4.3 NSE pre-open CSV import

The CSV is a universe-selection input, not a source of authoritative daily or minute OHLC. Its prices and turnover never replace Dhan's strategy inputs.

Controls:

| Setting | Default | Rule |
|---|---|---|
| Universe | Cash | `cash` selects symbols absent from the app's F&O list; `fno` selects those present |
| Direction | Gainers | Gainers, losers or both; also apply signed numeric bounds |
| Minimum turnover | 0 crore | Inclusive lower bound |
| Maximum turnover | Unbounded | Inclusive upper bound; must be ≥ minimum |
| Minimum change | 0% | Inclusive signed lower bound |
| Maximum change | Unbounded for gainers | Inclusive; required for losers/both |
| Top N | All matches | Positive whole number; apply after classification/filtering/sorting |

For losers use a negative interval such as −5% to −1%. Zero is included if the chosen direction and numeric boundaries permit it. Gainers cannot have a negative minimum. Losers require a maximum ≤0. Both requires an explicit maximum. F&O refers to equity underlyings in a static 210-symbol list, not derivative contracts or a guaranteed current exchange membership feed.

Processing order:

1. Validate UTF-8 CSV, maximum 2,000,000 bytes and at most 20,000 nonblank rows.
2. Remove BOM and normalize header whitespace/case; reject duplicate headers.
3. Locate symbol, percentage-change and value/turnover columns. Do not substitute rupee `CHANGE` for `%CHANGE`.
4. Parse finite numbers, Indian grouping commas, optional currency/percent/crore suffixes.
5. Normalize turnover units based on headers/export layout. Explicit crore columns stay in crore. Explicit rupee columns are divided by 10,000,000. Bare `VALUE`, `TOTAL VALUE` or `TURNOVER` with `FINAL PRICE` and `FINAL VOLUME` means rupees. Do not guess units from the value's magnitude.
6. Validate symbols; skip malformed rows, missing/invalid change or turnover and negative turnover. Keep the first valid occurrence of each duplicate symbol.
7. Apply numeric and direction filters, then Cash/F&O classification.
8. Sort pre-open turnover descending, then limit to Top N.
9. Return counts of total/valid/invalid/duplicate/numeric matches/classified matches/selected rows, units, and selected symbols.

Display price prefers Final Price, then available IEP/price fields. Missing display price does not discard an otherwise valid row.

`Filter CSV` previews only. Input changes invalidate the previous result and trigger a 300ms-debounced preview. Revision counters prevent an older asynchronous response overwriting a newer selection. `Use matches in scanner` applies the preview settings, replaces the stock list and saves the original CSV text, filename and filters in `config-preopen.json`. Empty matches cannot replace the list. A page reload restores the saved import and recomputes its preview.

## 5. Market data, dates, candles and arithmetic

All session decisions and visible trading times use `Asia/Kolkata` (IST). Browser-local timezone must not change the selected trading date. Historical timestamps are converted to aware IST datetimes. A candle's start identifies its minute; its end is start +1 minute.

Normal market opening minute is 09:15–09:16. The scanner supports historical Dhan responses containing a 09:14 opening label: its opening selector prefers 09:14 if present, otherwise 09:15. This is an explicit provider-compatibility behavior, not permission to create a premarket candle from live quotes. The displayed opening timeline contains at most five candles starting from the selected opening candle.

Definitions:

| Symbol | Meaning |
|---|---|
| `O1,H1,L1,C1,V1` | First completed opening candle open/high/low/close/volume |
| `P` | Previous completed trading session's close |
| `PDH,PDL` | Previous completed trading session's high and low |
| `A1` | Mean first-candle volume from three valid earlier sessions |
| `Vd` | Previous completed daily candle volume |
| `Ad` | Mean volume of the three daily sessions immediately preceding that daily candle |
| `LTP` | Latest accepted live traded price |

Key arithmetic:

```text
1 crore = 10,000,000 rupees
First-candle turnover = V1 × C1
Latest completed minute turnover = minute volume × minute close
Vol SMA / first-minute ratio = V1 / A1
Previous-day SMA = Vd / Ad
Previous-day change % = (P − prior-session close) / prior-session close × 100
Live change % = (LTP − P) / P × 100
Absolute opening gap % = abs(O1 − P) / P × 100
```

Three crore is **30,000,000**, not 300,000,000. Turnover is a candle approximation using close × shares, not the exact sum of execution values inside the minute.

Green means `close > open`; red means `close < open`; doji means equality. Open=high/open=low setup comparisons use the parsed candle values. Most crosses are strict, whereas specified maximum limits are inclusive. Preserve each boundary explicitly; do not apply a universal tolerance or rounding rule.

Reject nonfinite/nonpositive OHLC, negative or fractional minute volumes, unequal response-array lengths and invalid OHLC geometry. Daily parsing excludes the scan date and later sessions, validates duplicates and requires four completed sessions for the base daily filter. Optional inputs may require more history. Missing data is a separate unresolved state, not a zero-valued valid sample or an automatic failed condition.

## 6. Scanner setup qualification

### 6.1 Common base calculations

The daily condition is:

```text
(Vd / Ad <= daily_volume_max)
OR
(previous-day signed close-to-close change <= +1%)
```

Default daily maximum is 4×. The exception includes negative previous-day moves. It is not `abs(change)<=1%`, and it does not compare today's open with yesterday's close.

Opening-volume history uses three valid prior sessions, not simply three calendar days. Skip sessions missing the opening candle, zero opening volume and heuristic price-locked opening-circuit sessions. The locked-session heuristic requires essentially no opening range and an absolute opening gap within 0.35 percentage points of 2/5/10/20%; it is only a historical-sample exclusion heuristic, not verification of today's circuit band. Continue backward to obtain three valid samples.

Default first-minute multiplier is 4×. Equality passes: `V1 >= 4*A1`. Default first-candle turnover threshold is ₹3 crore. Equality fails: `V1*C1 > 30,000,000`.

### 6.2 Possible Candidate

All these base conditions must hold:

1. The first opening candle is green.
2. The daily condition passes with usable dated history.
3. First-minute relative volume reaches its configured minimum.
4. First-candle turnover is strictly above its configured threshold.
5. All enabled filters applicable to Possible Candidates pass.

Only the first candle is needed for the base setup. A break of the first high is **not required** unless some later added rule explicitly says so; it is normally an extra badge. Resistance ON can postpone qualification until LTP clears the selected resistance threshold. A stock without a first-high break can still be a Possible Candidate with other badges.

### 6.3 Redwala Gira

Base conditions:

```text
C1 < O1
O1 == H1
V1 × C1 > first_candle_turnover_min
```

Apply the optional Redwala previous-close filter only when enabled. Do not apply the daily-volume or minute-volume multiplier filters. Therefore Redwala may validly display a Vol SMA of 1.57× even when the global minute minimum is 4×. The value is informative for Redwala, not a condition.

Redwala is also exempt from Today Open Cross, Monthly, Last 2 Days, PDHL, Possible Candidate opening gap and Daily Resistance. Missing history needed only by those other setups must not prevent base Redwala qualification. However an enabled Redwala price filter needs its own valid previous close, and PDL badges need previous low.

### 6.4 Retest Break

Base first candle must be red; it need not open at its high. Daily filter, opening-volume multiplier, turnover and enabled Today Open Cross/Monthly/Last 2 Days conditions apply.

Starting from the immediately following minute, require consecutive completed green candles with no missing minutes. Confirm at the first candle whose high strictly exceeds the first candle high and which closes green. Any red/doji before the break permanently rejects the pattern for that session. Missing minutes leave it unresolved rather than proving either success or rejection. A red candle after an already confirmed break does not erase the result.

It can require many minutes, so it generally appears later than first-minute setups. Retest scanning continues beyond the five displayed candle cards. Its confirmation uses completed historical candles; sparse quote observations cannot prove an uninterrupted sequence. Retest Break has no Start Algo action.

### 6.5 Scope matrix

| Condition | Possible | Redwala | Retest |
|---|---|---|---|
| First candle green | Required | No | No |
| First candle red | No | Required | Required |
| First open=high | No | Required | No |
| Daily ratio OR +1% exception | Required | Exempt | Required |
| First-minute relative-volume minimum | Required | Exempt | Required |
| First-candle turnover minimum | Required | Required | Required |
| Today Open Cross / Monthly / Last 2 Days | If ON | Exempt | If ON |
| Possible opening-gap / PDHL / Resistance | If ON | Exempt | Exempt |
| Redwala previous-close/tolerance | Exempt | If ON | Exempt |
| Absolute volume / maximum-price display filters | If ON | If ON | If ON |

## 7. Optional daily and opening filters

All scanner toggles below default OFF. Settings persist on the server. Percent limits use percentage points, e.g. 1 means 1%, not 0.01. The exact JSON defaults and constraints are included in the companion files.

### 7.1 Today Open Cross

For Possible Candidates and Retest Break:

```text
O1 > maximum(close of five completed trading sessions before the target date)
```

Equality fails. Missing five dated closes stays unresolved. These inputs can be prepared before opening; the actual first open is observed later.

### 7.2 Monthly Filter

For Possible Candidates and Retest Break, require first open strictly above the maximum daily **close** from the last 20 completed trading sessions. Despite the label, this is not a calendar-month candle, 20 calendar days or 20 highs. Missing required history is unresolved.

### 7.3 Last 2 Days Filter

For Possible Candidates and Retest Break, inspect the prior two completed daily open/close pairs:

- Both strictly green: no extra opening constraint.
- Either red or doji: `O1 > max(the two closes)`.

Missing pairs remain unresolved. Equality to the required maximum fails.

### 7.4 Open / Previous Close — Possible Candidates only

Default limit 1%. When ON:

```text
abs(O1 − P) / P × 100 <= possible_open_pre_close_max
```

Both gap-up and gap-down are checked. With P=200 and 1%, opens 198 through 202 pass; 202.01 fails. Do not use previous-day percentage change or first close in this calculation. Live, scanner backtest and algo backtest setup qualification share the rule.

### 7.5 PDHL — Possible Candidates only

Default maximum 4%. When ON:

```text
(PDH − PDL) / PDL × 100 <= pdhl_max
```

Use low as denominator, not previous close or high. Equality passes. Require same-session dated valid high/low with high≥low. Redwala and Retest are exempt.

### 7.6 Redwala Open or Close / Previous Close

Default distance limit 1%. With the parent toggle ON:

```text
close condition: C1 < P
opening condition with tolerance OFF: O1 > P
distance condition: min(abs(O1−P), abs(C1−P)) / P × 100 <= limit
```

Either opening distance **or** closing distance can pass; both are not required. Example: P=200, O1=201.50, C1=195, limit 1% passes the distance check through the open, despite the close being 2.5% below P. Base Redwala rules still apply.

### 7.7 Redwala opening tolerance

Default OFF; default tolerance 0.5%. Effective only while the parent Redwala filter is ON. Replace the strict opening condition with:

```text
(O1−P) / P × 100 >= −tolerance
```

An opening equal to P is allowed. With P=200 and 0.5%, O1=199 passes the opening test, 198.99 fails. There is no extra upper bound from this tolerance rule. The separate open-or-close distance condition and strict `C1<P` still apply, as do red candle, open=high and turnover. Parent OFF bypasses the entire additional rule.

### 7.8 Saving settings

Save & Apply validates/persists a frozen settings object, reevaluates cached daily decisions and confirmed candles, and schedules missing prerequisites in background workers. The save itself performs no Dhan network work or whole historical-cache rewrite. It does not restart the active scanner feed.

The browser distinguishes edited controls from saved settings, prevents overlapping saves, limits the save response wait to 10 seconds and avoids overwriting unsaved edits with polling responses. A timeout does not necessarily cancel server work. Scanner backtests save the visible controls before starting and send a settings snapshot with the request. Existing results show the parameters they actually used; rerun to change qualification. Active algo sessions retain their execution settings.

## 8. Daily resistance algorithm

Applies only to Possible Candidates. Defaults: OFF, search lookback 60 trading sessions, 2 left and 2 right confirmation candles, age 4–60, breakout buffer 0%, optional pullback OFF with 3% stored value.

Validation: lookback 5–252; left/right 1–10; ages 1–252 and `min_age <= max_age <= lookback`; right confirmation count must be less than maximum age; buffer and pullback 0–100%.

### 8.1 Selecting a historical level

Use completed daily candles strictly before the target date, sorted by distinct date. Preserve enough request capacity for lookback plus left-side context. When enabled, the requested calendar window is `max(90, (lookback+left)*2+30)` days; actual trading sessions determine age.

For every candidate peak in the lookback:

1. It has the required earlier and later daily neighbors.
2. Its high is strictly greater than all left and right neighboring highs; equal neighboring highs invalidate the swing.
3. Age is within the configured inclusive bounds. Previous trading session has age 1.
4. Peak high is at or above previous close.
5. No subsequent completed daily close is strictly above that peak high; such a close retires the old resistance.
6. If minimum pullback is enabled, require `(peak high − minimum subsequent daily low)/peak high*100 >= minimum`.

Select the lowest eligible overhead high. If highs tie, prefer the younger peak. Return raw level, peak date, trading-session age, pullback percentage and buffered threshold:

```text
threshold = resistance_level × (1 + resistance_buffer/100)
```

Short listing history is allowed; a recently listed stock can have a valid peak if it has sufficient neighbors/age. Do not require 60 actual bars just because lookback is 60. Valid history with no eligible peak returns `no_level` and fails the enabled resistance filter. Missing/invalid/inadequate requested coverage returns `unresolved`; these are different outcomes.

Selection is memoized with an LRU cache of 2048 combinations. Live ticks compare prices to a cached selected threshold; they do not download or rescan daily history.

### 8.2 Live qualification

After all non-resistance Possible Candidate conditions pass, require current LTP strictly above the threshold. It can qualify later in the day. If LTP returns to/below the threshold, current resistance-dependent qualification disappears. This is not a sticky event like the first-high-break badge. A previously started algo continues independently.

### 8.3 Backtest qualification

Require a completed **green** minute candle close strictly above the threshold, using historical resistance selected only from earlier sessions. Record the first qualifying candle's end as `resistance_break_at`. Algo qualification may use only candles completed by the selected entry time, preventing a breakout later in the day from authorizing an earlier entry.

### 8.4 Resistance Break Open badge

Only candle 1 or 2 can earn this badge. Its open must be strictly below the raw resistance. It must cross strictly above the buffered threshold. Live uses observed intraminute high or repaired historical high; replay requires that candle's close above the threshold. Gap-open above resistance cannot earn this particular badge. It may still earn general Resistance Break. Preserve these live/replay differences rather than pretending tick order is available from OHLC.

## 9. Badge rules and sorting

| Badge | Scope and rule |
|---|---|
| Possible Candidate | Confirmed green-first setup qualification |
| Redwala Gira | Confirmed red/open=high setup qualification |
| Retest Break | Confirmed uninterrupted-green sequence after first red |
| Open = Low | Possible Candidate with O1=L1 |
| `under_3.5%` | Confirmed Possible Candidate with `abs(O1−P)/P*100 <= 3.5`; independent of the opening-gap toggle/value |
| Previous day high cross | Possible Candidate with `O1 < PDH < C1` |
| First Candle High Break | Possible Candidate; a later live price/minute high strictly exceedsH1; retained after pullback |
| First Candle Low Break | Redwala; a later live price/minute low strictly falls below L1; retained after rebound |
| First Candle PDL Cross | Redwala with `C1 < PDL < O1` |
| PDL Cross on 2nd Candle | Redwala; immediately following completed candle has `C2 < PDL < O2` |
| Resistance Break | Enabled resistance condition using live LTP or a completed green replay close |
| Resistance Break Open | First/second opening-cross rule from section 8.4 |
| F&O | Symbol belongs to app's classification list; informational |
| Awaiting confirmation | Live-derived provisional match, not a confirmed historical signal |

Touches/equality do not count for strict PDH/PDL crosses or first-high/low breaks. A later intraminute dip below PDL is not a first-candle or second-candle close cross. Do not render a duplicate generic Previous Day Low Break badge beside the requested strict-cross badges. A legacy response field can remain for compatibility without being a displayed badge.

`under_3.5%` uses positive finite first open and previous close and a tiny floating-point boundary allowance. It does not change qualification, resistance or priority. Provisional rows do not receive it as a final badge.

### Live ranking — exact combination rules

1. First group: Possible Candidate **AND** Resistance Break **AND** Resistance Break Open **AND** First Candle High Break. All four required.
2. Second group: Redwala Gira **AND** First Candle Low Break **AND** First Candle PDL Cross. All three required. PDL Cross on 2nd Candle is optional and does not create a higher group.
3. Remaining results, including partial combinations and provisional matches.

Inside each group, first-candle turnover descending; equal turnovers preserve previous order. A partial combination, Open=Low, F&O, PDH-cross or `under_3.5%` does not independently earn a priority group. Do not replace these rules with a count of badges or simple alphabetical setup sorting.

Backtest ordering has a compatibility difference: the backend orders Possible Candidates first and then minute-volume multiplier descending. The browser uses the live priority/turnover comparator for backtest rows when either local volume or price display filter is enabled; otherwise it retains backend order. A rebuild seeking exact parity must retain this distinction or explicitly version a change.

## 10. Dashboard and browser behavior

### 10.1 Main controls

The page contains: connection/updated time, Dhan Login, Stocks and cache buttons, scanner statistics/start/stop/repair, CSV selection, Scanner Filters, Live/Backtest tabs, setup selector, local Display Filters, live/backtest tables, Algo settings/session cards and Algo Backtest.

Live table column order:

```text
Rank | Stock & Badges | 1st Turnover | Vol SMA | LTP | % Change
| UC Away % | LC Away % | First Candle | Open Volume | 3D Avg
| Prev Day SMA | Prev Day % | 1m Turnover | 1m Volume | Candle
| Prev Close | Status
```

Stock/badges and first turnover use pinned/sticky presentation so key information is accessible without scrolling to the far right. Vol SMA immediately follows first turnover. The first five opening-candle turnover cards wrap on small screens. Keep badges under the symbol/name and Start Algo alongside the selected row. Escape symbols, names, provider messages and filenames before injecting HTML.

### 10.2 Statistics and status

Qualified counts count each matching stock once even if more than one setup is true. Show prepared/day-filter-failed/unresolved/provisional/confirmed context. A daily-filter failure means excluded from the volume-based setups, **still scanned for Redwala**. Display visible/hidden counts separately from backend qualification totals.

`Prev Day %` is yesterday's close-to-close move, not today's opening gap. Backtest first-candle details also show first open, first close, previous close and actual absolute opening gap to prevent confusion.

### 10.3 Local display filters

These do not alter backend qualification, history preparation or an active algo. They apply immediately to existing Live and Backtest results without a rerun. Store shared preferences in auth.sqlite3; browser localStorage is not authoritative. Only administrators can edit them. Invalid drafts retain the last valid configuration.

| Filter | Default | Live input | Backtest input | Comparison |
|---|---|---|---|---|
| Absolute first volume | OFF; 100,000 shares | `today_opening_volume` | `first_candle_volume` | Strictly greater than threshold |
| Maximum stock price | OFF;₹250 | LTP | First-candle close | At or below maximum |

Both combine with the setup selector. Enabled filters hide missing inputs. Volume thresholds are nonnegative integers; price maximum is nonnegative; a zero maximum hides all positive-priced stocks. **The price filter is an upper limit, not a minimum-price filter.** Both apply to Redwala too, despite Redwala's exemption from relative-volume qualification.

### 10.4 Polling and form stability

The browser polls `/api/state` about every 2 seconds and permits only one state request in flight. Form hydration must not overwrite edits on every poll. Initial credential/settings loading is distinguishable from defaults. Save failures preserve edits and display an error. A stale backtest label identifies changed inputs; do not merely relabel old results with new parameters.

### 10.5 Existing circuit-distance columns

Fresh upper/lower prices come from Dhan full quote responses for qualifying stocks. Requests are batched and eligible refreshes use 60-second per-stock intervals through the shared quote throttle. A worker checks for newly qualified stocks every two seconds. Data from another date or older than 120 seconds is not displayed as current.

```text
UC Away % = (upper circuit − LTP) / LTP × 100
LC Away % = (LTP − lower circuit) / LTP × 100
```

Example:reference close 100, upper 120, lower 80, LTP110 gives UC Away 9.09% and LC Away 27.27%. These are distances from LTP, not the nominal 20% band. At a limit the distance is 0%, which does not prove the stock is locked. Missing/invalid quotes and LTP outside returned limits suppress misleading distances and show status. Today's circuit limits are not persisted for historical filtering.

## 11. Preparation, live confirmation and request scheduling

### 11.1 Premarket preparation

`Cache Volume + Day Levels` works per stock:

1. Reuse dated valid daily history or fetch missing history.
2. Compute daily ratio/exception and cache previous close/high/low plus enabled filter inputs.
3. If the daily condition passes and needed prerequisites are ready, obtain/reuse the three valid opening samples and required opening-volume threshold.
4. Publish ready state immediately in memory.
5. Batch prepared-snapshot writes; move to the next stock. Retry unresolved stocks, not the full successful universe, for up to three preparation passes.

Daily failures do not need opening-volume history merely to detect Redwala. They remain in the subscribed universe. Missing/error is unresolved, not a genuine daily rejection. The preparation action can run before or during market hours; its history always excludes the target session for historical inputs.

### 11.2 Live opening sequence

Before 09:15 subscribe all configured stocks in Dhan Quote mode. Premarket cumulative volume supplies a baseline, not a fake opening candle. During the first minute construct sampled OHLC and volume deltas while recording feed completeness.

A timer at the minute boundary initiates local screening even if a stock does not trade again. Prioritize likely matches for historical confirmation. Show live matches as Awaiting confirmation; only confirmed candles authorize final setup state and Start Algo.

Sampled feed data can miss highs/lows or volume boundaries. A low-volume exclusion without REST is allowed only when a complete conservative bound proves volume below threshold. The bound includes trades through the first boundary quote, so extra second-minute trades cannot cause a qualifying first minute to be underestimated. Late joins, missing baseline/boundary, delayed frames, cumulative resets and disconnects require historical confirmation. Apparent colour/turnover failure from sparse OHLC alone cannot safely discard a stock.

### 11.3 Confirmation/recovery

Fetch completed opening history for likely matches and incomplete observations. Missing prerequisites are prepared as needed. Confirmation retries skip already completed/rejected stocks, use per-stock locking to avoid duplicate preparation, and retry unresolved entries with backoff capped at 30 seconds until stop or 15:31 IST. Fatal authentication/rate errors stop the affected batch.

If a narrow request lacks 09:14/09:15, try one wider recovery window from the preceding calendar day to now. Later retries use recovery directly. Record request range, candle count and returned timestamp bounds in logs and SQLite `opening_diagnostic`. Do not synthesize a successful opening candle from later data. Repair + Check Open fetches missing candles and reruns opening checks manually.

Retest and circuit workers run separately from automatic opening confirmation. Stopping live signals workers, invalidates old feed state and uses bounded SDK shutdown rather than allowing an indefinite close call.

### 11.4 Rate scheduler

| Channel | Application spacing | Sharing |
|---|---|---|
| Daily/minute history |0.23 seconds minimum between starts | Preparation, confirmation, repair and historical scans share scheduler |
| Full quote/OHLC |1.05 seconds | Circuit and algo fallback quote work share scanner quote throttle |
| Algo order/portfolio operations |0.22 seconds | Serialized aggregate broker adapter calls |

History requests are serialized, so response latency can reduce throughput below 1/0.23≈4.35 requests/second. These are application's configured spacings, not a promise of broker throughput or a current broker limit certification.

Priority fairness: serve up to three waiting high-priority confirmations, then give a waiting background request a turn. Idle priority workers reserve no slots. An already-running request is not preempted. This prevents confirmations from starving missing preparation.

Preserve bounded rate-error retries/backoff: OHLC/intraday rate retries use 1.5 and 3-second waits; daily retry waits use 1.25 and 2.5 seconds. Remove redundant per-stock 1.15-second sleeps; do not remove provider backoff. Historical retries and order-submission retries are different: uncertain orders must not be blindly resent.

### 11.5 Latency expectations

The design aims for progressive useful results shortly after 09:16, not a hard deadline for every stock. For 266 stocks, an entirely cold cache with one daily and one opening-history request per stock implies 532 calls: the 0.23-second start-spacing floor alone is about 122 seconds, before serialization of slow responses, retries, extra windows and competing work. Warm dated caches greatly reduce this. Confirmation of a small list is faster than refetching all stocks at 09:16. Local comparisons are generally much cheaper than the network work.

## 12. Storage and cache contracts

| Path | Contents | Handling |
|---|---|---|
| `data/config.json` | Credentials, symbols, scanner filters | Small atomic JSON replacement; private |
| `data/config-preopen.json` | Saved CSV text/name and import settings | Separate atomic JSON replacement; may contain user data |
| `data/config-cache.sqlite3` | Prepared inputs, previous closes and raw historical samples | WAL SQLite; incremental updates |
| `data/api-scrip-master.csv` | Downloaded Dhan master | Renewable source cache |
| `data/nse-equity-instruments.json` | Resolver index | Derived source cache |
| `data/algo.sqlite3` | Algo defaults, sessions, order intents/fills/events | Durable execution journal; never treat as disposable cache |
| `data/algo.sqlite3.lock` | One-process ownership handle | OS lock; not an authentication mechanism |

History tables:

```sql
CREATE TABLE prepared (
  symbol TEXT NOT NULL, session TEXT NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY(symbol, session)
);
CREATE TABLE closes (symbol TEXT PRIMARY KEY, price REAL NOT NULL);
CREATE TABLE history (
  kind TEXT NOT NULL, instrument TEXT NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY(kind, instrument)
);
```

Prepared payloads retain daily-filter data, volume samples/average, preparation state and timestamps. `prepared` keeps recent snapshots, pruning entries older than 14 days relative to the incoming session for that symbol. Loading chooses the latest session per symbol. Cache validity still has to be checked against the requested date; loading the newest row does not automatically make it valid.

Raw `daily` payloads carry version, requested start, coverage-through date and dated OHLCV bars. Raw `opening` payloads carry version, coverage-through date and retained opening/last bars across prior sessions (up to 60 retained dates). `opening_diagnostic` stores request recovery evidence. Newer coverage cannot be overwritten by an older replay write.

On rollover, reuse dated samples and fetch the last known daily bar plus newer data or the missing opening-history date range. Validate coverage, shapes, prices, session order and required count/capacity. Empty incremental data prompts a wider check rather than assuming a holiday. Recompute rolling values for the target date; do not reuse yesterday's qualification decision.

Prepared snapshots flush after 25 accumulated stocks or 2 seconds of ongoing work, plus a final flush on completion/error. This is not a promise of a standalone 2-second persistence timer while idle. In-memory updates are available before the next bulk persistence operation. Compare `cached_at` to prevent delayed older writes overwriting newer snapshots.

Legacy large JSON cache fields migrate into SQLite before being removed from configuration. Transaction ordering preserves retryability if replacing JSON fails. Config-only settings/credential operations avoid loading or rewriting bulk caches.

Algo tables: `sessions(id,payload)`, `events(id,session_id,payload)`, `settings(id,payload)`. Use WAL and synchronous FULL, commit intent before submission, and preserve sessions across restarts. Windows uses a byte-range lock; POSIX uses flock. Another execution owner must fail clearly instead of creating two senders.

## 13. Scanner backtesting

The standard scanner backtest accepts one target date within the previous 60 calendar days, including today if completed data is available; future dates fail. This is an app restriction and is different from the larger algo-backtest date allowance.

It requires credentials and resolved symbols, not a live scanner connection or prior manual cache action. For each stock:

1. Fetch minute history including target session and earlier samples.
2. Rebuild target-relative daily and opening-volume inputs using only prior sessions.
3. Parse completed candles and determine base setup plus optional filter qualification.
4. Compute later badges and Retest sequence from the available target-session history.
5. Return a row with inputs, setup flags, reasons and any error/data warning.

A daily-history failure can still produce turnover-only Redwala when its optional previous-close filter is OFF; missing history suppresses dependent badges and produces a warning. Authentication/rate errors stop batches rather than hammering all remaining symbols. Individual data failures are surfaced as incomplete results; zero matches and failed data retrieval are not equivalent.

The result includes target date, immutable settings snapshot, rows, tested count, legacy `four_x_count` (minute multiplier qualifiers using the configured threshold), candidate/qualified/Redwala/Retest counts, errors and warnings. `qualified_count` is what the dashboard uses for the combined setup count. Do not infer a permanently fixed 4× threshold from the legacy field name.

Display volume and price filters can rerender an existing result instantly. Qualification changes require a rerun. Circuit distances/band qualification are not reconstructed from today's quotes. A later first-high break in a whole-day scan is a retrospective badge, not evidence it was available at 09:16. Algo qualification has a stricter selected-entry-time cutoff.

## 14. Selected-stock algo trading

### 14.1 Start conditions and controls

Only a confirmed current-session Possible Candidate or Redwala can start an algo from the live table. The server rechecks eligibility; a button is not authorization proof. Start is allowed from 09:16 until that session's configured square-off. A same-stock/mode/account unfinished session blocks another start. After a target or maximum-loss day lock, that stock/mode/account cannot restart that day.

Paper is selected on each new browser load. Switching to LIVE and accepting the per-stock confirmation sends real-order requests. Changing the mode control affects future starts only. Paper mode still needs credentials and fresh market data. No stock begins automatically when the page opens or a scan matches.

Visible defaults:

| Control | Default | Meaning |
|---|---|---|
| Execution mode | Paper | Paper or live orders |
| First direction | Setup | Candidate long, Redwala short; override long/short for either |
| Capital per entry/add |₹10,000 | Divide by execution-side price and floor shares |
| Target |4% | Relative to original completed entry of current ladder |
| Stop/add interval |1% | Fixed stop distance and favorable next-add increment |
| Trailing |OFF; 1% | Follow best observed LTP, never loosen |
| Ladder reversals |OFF | Reverse on SL/TSL when enabled and allowance remains |
| Pyramiding |OFF | Add equal capital at successive favorable thresholds |
| Maximum adds |2 | Resets for a new ladder |
| Maximum reversals |20 | Session-wide limit |
| Maximum session loss |₹10,000 | Net marked P&L condition, not guaranteed maximum realized loss |
| Square-off |15:15 IST | Valid 09:17–15:20 |
| Slippage |5 basis points | Paper/replay execution-price adjustment |
| Cost per filled order |₹0 | Configurable flat estimate |

Additional API defaults: order timeout 15 seconds (5–60), quote maximum age 5 seconds (1–30), quantity 1 (1–100,000). The API model also accepts quantity sizing, average-price reference and accumulated reversal size, but the dashboard explicitly sends **capital**, **original**, **initial**. Exact UI replication must not silently replace the user's chosen semantics with those advanced alternatives.

### 14.2 Quantity and fills

Initial long quantity is floor(capital/ask); short quantity is floor(capital/bid), without assumed leverage. If below one share, reject. Each add uses the same capital at its own fresh execution-side quote; share count can change as price moves.

A fill updates actual net shares and weighted average. Adding in the same direction updates average; closing realizes profit against that average; crossing through zero creates an opposite position. Partial fills are applied individually, deduplicated by fill identity. The completed entry/reversal sets the ladder's original reference to its completed entry average. Targets/fixed stops stay tied to that reference under the UI's original-price setting, while cost basis for P&L remains weighted average.

### 14.3 Target, stop and trailing

For direction `s=+1` long or `−1` short and original entry E:

```text
target = E × (1 + s × target_pct/100)
fixed stop = E × (1 − s × stop_pct/100)
trailing candidate = best observed price × (1 − s × trailing_pct/100)
```

Long best is maximum observed LTP; short best is minimum. Long stop is the maximum of fixed/trailing/existing stops; short stop is the minimum. Disabling trailing leaves the fixed-stop mechanism. A target closes all shares and locks trading for that stock/mode/account that day.

Decision order: initial entry; while positioned, square-off, maximum-loss, target, stop/reversal, then add. Inclusive risk-threshold comparisons have small numerical allowances. Do not let an add override a pending protective exit.

### 14.4 Ladder reversal and pyramiding

With ladder OFF, SL/TSL exits the position and ends the session. With ladder ON and reversal count available, desired net position becomes the opposite initial share quantity.

Example: initial long 500, accumulated long 1,500 after adds, desired short 500. Submit one SELL 2,000 order, not a close order followed by a second entry order. Reconcile all actual fills; do not assume the order filled instantly or fully. A target never starts an opposite ladder. Reaching the maximum reversal count converts subsequent stop behavior to an exit.

With pyramiding ON, first add trigger is one stop-percent favorable move from completed entry average. After a confirmed add, next trigger is one stop-percent favorable move from that add's actual average fill. This compounds; it is not always an arithmetic 1%, 2%, 3% from the first entry. Count one add per completed add order and stop at maximum adds.

## 15. Order handling and reconciliation

### 15.1 Market triggers and execution data

A dedicated Full market websocket provides selected algo stocks? LTP and five levels of depth, independently of the scanner feed. Every accepted fresh tick updates risk locally; no disk or broker REST work runs on that receive path. Latch the first exit/reversal so a later recovery does not erase a touch. Observations are tied to the exact fill/pending-order generation to prevent old ticks acting on a new ladder.

Use fresh cached bid/ask for execution estimates and sizing. If LTP/depth is missing/stale, a separate worker requests full quotes using the shared 1.05-second quote throttle. It does not block tick reception. Ignore malformed, stale, out-of-order packets and older REST responses that would overwrite newer websocket depth. Check LTP timestamp and depth timestamp independently. Positive bid≤ask is required for usable depth.

Dhan Full protocol in this implementation uses request 21 subscription/22 unsubscription in batches 100; NSE segment 1 and response code 8 with 162-byte full packets. A disconnect packet 50 triggers reconnect. The market feed reconnect delay grows 1→2→…→30 seconds. These are the pinned integration's wire assumptions; verify them before upgrading broker/SDK versions.

After a trigger, a worker executes; tick detection does not guarantee immediate broker fill. New exposure needs fresh depth and an available order-update connection. A live flatten to desired zero can proceed without depth after reconciliation; paper fills require a valid price. If neither websocket nor REST delivers prices, new price crossings cannot be detected.

### 15.2 Order intent lifecycle

```text
queued -> fresh quote / preflight -> durable intent (SUBMITTING)
 -> broker acknowledgement or UNCERTAIN
 -> pending / partial fills -> terminal reconciliation
 -> running opposite/added ladder, done, or paused with exposure issue
```

Preflight checks account identity, actual NSE_EQ INTRADAY broker quantity versus app quantity, and external pending orders in the same instrument/product. A mismatch pauses; do not trade away unexplained external shares. Running manual orders in the same stock/product can violate this ownership assumption.

Persist a unique correlation-tagged intent before sending. Submit MARKET, INTRADAY, DAY, NSE_EQ, price 0, not AMO, without automatic slicing. Signed delta is desired net minus actual app net. An acknowledgement is not a fill.

If submission response is missing/ambiguous, mark UNCERTAIN and look up by correlation ID. **Never automatically repeat a potentially accepted order.** A browser timeout similarly instructs the user to inspect session state before retrying.

The order socket connects separately and receives order alerts; alerts wake the worker. REST order/trade/position data are authoritative for fills. Duplicated/out-of-order websocket messages must not increment quantity.

### 15.3 Reconciliation and partial fills

Validate order ID/correlation, account when provided, instrument, product, direction and intended quantity. Validate each trade identity and positive integral traded shares. Require exchange trade ID for deduplication; reject changed previously applied trades or fills exceeding submitted quantity.

Apply new trades, persist each verified fill, and compare summed trades with order-reported `filledQty`. Temporary disagreement stays pending. After terminal status verify broker quantity equals app quantity. Terminal statuses are TRADED, CANCELLED, REJECTED, EXPIRED.

Only a fully filled TRADED intent completes its intended strategy action. A partially filled terminal entry/add/reversal must not start a replacement ladder as if complete: flatten actual reconciled residual exposure. If the attempted exit itself is rejected/partial with exposure remaining, pause and require explicit Exit & Stop retry rather than generating endless orders.

Pending orders can request cancellation for timeout, user exit, square-off or risk touched during partial fills. Retry cancellation with a 5-second interval, at most 3 attempts. Wait for terminal status and verified fills before replacement/flattening; a cancellation acknowledgement alone does not prove no more fills occurred. The SDK adapter handles successful empty 202/204 cancellation responses.

### 15.4 Restart, commands and ownership

On startup unfinished persisted sessions become paused with explicit reconciliation instructions. Reconcile & Resume checks broker state before continuing. Exit & Stop cancels pending remainder, reconciles and flattens app-owned exposure. Scanner Stop does not call this.

The session journal has exclusive OS-level process ownership. Run no duplicate execution processes, reload workers or multi-worker deployment. Shutdown stops workers/connections; it is not a broker-hosted flatten guarantee. Prior-day residual exposure does not trigger automatic overnight orders; reconcile it explicitly.

## 16. Algo historical replay and P&L

### 16.1 Qualification and date rules

One stock, setup (`possible` or `redwala`), target date and selected entry time. First direction is independent of selected setup. Validate the setup using saved scanner rules and only candles completed before entry. First-high-break is not mandatory for a base Candidate.

Algo backtest accepts a date up to 5×366 days before today in the inspected source, subject to actual broker data availability. Standard scanner backtest remains 60 days. Entry time 09:16 to before 15:20 and strictly before square-off. Replay always forces paper, even if LIVE was selected in the form.

Require the selected entry candle and contiguous available minutes thereafter. Missing interior minutes fail reliable replay. A shortened tail can close at last available close and is marked truncated/incomplete, with `complete_through`. Do not call a shortened session a full-day outcome.

### 16.2 Initial entry minute

Initial entry fills at selected candle open, adjusted for slippage. For post-entry decisions within **that initial candle**, inspect only the close. Ignore its high/low for stops, target, adds and trailing watermark. Close-triggered actions fill at close plus slippage and use candle-end timestamps. This applies regardless of candle colour; green does not prove an absence of earlier downward trades.

### 16.3 Later-minute OHLC assumptions

From the next candle onward:

- If open=high: path open→low→close.
- If open=low: path open→high→close.
- Otherwise long path open→low→high→close; short path open→high→low→close (adverse extreme first).

An opening extreme is already visited; do not invent a later revisit after entering/reversing. A recorded close can still represent a rebound. Process crossed strategy thresholds along this assumed path. Gap-triggered actions execute at the candle open, not an unattainable prior stop price. A transition guard rejects excessive intraminute events instead of looping indefinitely.

### 16.4 Backtest-only reversal confirmation

Reversible SL/TSL requires the candle close at/beyond the current stop. A touch followed by recovery does not reverse. Combined reversal fills at that close plus slippage, timestamped at candle end. Begin evaluating the new position with the next candle; never replay earlier extremes of the just-completed candle against it.

Targets, adds, maximum-loss exits and non-reversing stops after the initial minute retain OHLC modeling. Do not open an opposite position at square-off or the end of available data. Close remaining shares at end-of-data if still open.

Live/paper reversals remain immediate on received qualifying ticks. Therefore replay is intentionally not execution-equivalent to live. One-minute OHLC cannot reproduce ticks, order-book queues, partial-fill timing or actual slippage.

### 16.5 Slippage, fees and P&L

Paper buys use ask×(1+slippage_bps/10,000); sells use bid×(1−slippage_bps/10,000). Replay uses the simulated threshold/open/close in place of bid/ask. Five bps is 0.05%, not 5%. Slippage is already in fill prices; do not deduct it a second time from gross P&L. Live fills use broker execution prices rather than synthetic slippage.

Realized P&L from a closing portion:

```text
(fill price − prior average cost) × closed shares × prior direction
```

Open-position marked P&L:

```text
realized gross − accrued estimated fees + (mark price − average cost) × net shares
```

At fully flat replay completion:

```text
net P&L = cumulative realized gross P&L − estimated order costs
```

The fill table's gross P&L is **cumulative**, not profit earned separately on every row. Never sum that column. A combined reversal is one filled order for the flat-fee estimate, not two. A terminal partial order with some fills accrues its fee once; an unfilled rejection does not. Costs are configurable estimates, not a full brokerage/tax ledger.

Example: last cumulative gross ₹118.50, 18 filled orders at ₹7 each → costs ₹126, net−₹7.50. Present gross, costs and net together. Editing settings does not retrospectively change existing fills; mark results stale and rerun.

## 17. API and data contracts

All APIs are local JSON routes. FastAPI/Pydantic validate types/ranges; malformed bodies generally receive 422. Business validation maps to 400 on designated routes; some scanner/cache failures return 500. Mutations are POST, state/config GET. `/api/*` responses carry `Cache-Control: no-store`. All existing scanner, configuration, CSV, cache, backtest and algo APIs require an active admin session; mutations also require its CSRF token. /api/member/state requires an approved authenticated account and returns only whitelisted, filtered result fields. /api/auth/* implements password/TOTP login, signup, session identity and logout; /api/admin/users manages approval/suspension; /api/display-settings stores the shared display preferences. See MEMBER_HOSTING.md for exact security and operational behavior.

| Method/path | Purpose / payload |
|---|---|
| GET `/` | Dashboard HTML with hashed static URLs |
| GET `/api/config` | Saved filters, client ID, credential availability, universe text and cache counts |
| POST `/api/credentials` | `CredentialsIn`: client_id, access_token |
| POST `/api/symbols` | `SymbolsIn`: symbols_text |
| GET `/api/preopen` | Saved import and default CSV settings |
| POST `/api/preopen/preview` | `PreopenRequest`: csv_text, filename, settings; no universe mutation |
| POST `/api/preopen/apply` | Preview+replace universe+save import; rejects empty selection |
| POST `/api/volume-filters` | Complete `VolumeFilterSettings` object |
| POST `/api/cache` | Cache previous closes |
| POST `/api/cache-volume` | Prepare daily levels and opening-volume history |
| POST `/api/start` | Start scanner feed/workers |
| POST `/api/stop` | Stop scanner, not algos |
| POST `/api/repair` | Repair history and reevaluate opening checks |
| GET `/api/state` | Running/connected/status/time, stock rows, unresolved symbols, filters, algo snapshot |
| POST `/api/backtest` | target_date, optional opening scan_type and settings snapshot |
| POST `/api/algo/settings` | Save AlgoSettings for future sessions |
| POST `/api/algo/start` | symbol, setup, settings; returns queued session ID |
| POST `/api/algo/{session_id}/exit` | Request reconciled flatten |
| POST `/api/algo/{session_id}/resume` | Request reconcile then resume |
| POST `/api/algo/backtest` | AlgoStart fields plus target_date, start_time |

`/docs`, `/redoc` and `/openapi.json` are FastAPI's standard schema/documentation surfaces. The companion interface document inventories these routes from source and lists Python model fields. `MODEL_SCHEMAS.json` gives exact type/default/range/nullability information, including inherited fields.

### Principal domain records

- Instrument: symbol, name, security_id, exchange_segment, instrument_type.
- Candle: aware start, open, high, low, close, integer volume; derived end, colour, turnover.
- DailyVolumeFilter: target session, previous date, previous volume/close/high/low, prior close, three dated volume samples, average, multiplier, percent_change, passes, price_exception; optional five/twenty closes and last two candles. Raw resistance inputs are retained internally; selected resistance fields are exposed on rows.
- StockRow: instrument/price/latest candle fields, opening samples/average/volume/turnover, setup flags/reasons, badges, preparation/confirmation/provisional/completeness fields, fresh circuit prices/distances/errors and status.
- BacktestRow: target date, first-candle inputs, target-relative qualification/badges, errors/data warnings; no current LTP/circuit contract.
- Algo session: ID, stock/account/mode/setup/date, creation time, status/message, immutable settings inside strategy, pending intent, completed intents, quote, broker quantity, reconciliation time, exit/resume flags, P&L.
- Ladder state: initial side / base quantity / net quantity, average / original / best / stop / next add, add/reversal counts, realized/fees, started / done / day lock, last reason, fills.
- Fill: unique ID, signed quantity, price, time, resulting net quantity, cumulative gross; replay may add `candle_close` execution metadata.

Example scanner settings request, not a live broker action:

```json
{"daily_volume_max":4,"minute_volume_min":4,"first_candle_turnover_min":30000000,
 "possible_open_pre_close":true,"possible_open_pre_close_max":3.5,
 "resistance_filter":true,"resistance_lookback":60,"resistance_left":2,
 "resistance_right":2,"resistance_min_age":4,"resistance_max_age":60}
```

Omitted model fields default when constructing a new request model. To preserve current settings while editing one field, clients should send a complete current settings object; do not assume partial POST behaves as PATCH.

## 18. Error handling and troubleshooting

| Symptom | Interpretation / diagnostic path |
|---|---|
| DH-901 / Invalid Authentication | Credentials invalid/expired; save valid credentials, preserve existing execution identity/reconciliation |
| DH-904 / Rate Limit | Respect shared throttles/backoff; stop the failing batch instead of retrying every symbol |
| DH-905 / missing history | Inspect instrument ID, segment/type, date/window and response; do not declare a valid no-match |
| Long Awaiting confirmation | Inspect preparation state, opening baseline/boundary completeness, pending history, diagnostics and retries |
| Redwala below 4× | Expected if turnover/red/open=high pass; relative-volume filters exempt |
| Large Prev Day % despite gap limit | Different metrics; compare actual O1 and P, not yesterday's percentage |
| CSV filter shows same huge count | Check interpreted turnover unit/header and preview's applied settings; reapply corrected preview |
| Stock hidden despite qualifying | Inspect setup selector and local volume/price filters; counts are separate |
| Missing resistance level | Distinguish unresolved history from valid history with `no_level`; short listings need enough swing context |
| Two PDL labels appear | Strict first/second close crosses are distinct; generic later PDLbreak must not duplicate them |
| Old UI after copying files | Existing process may serve another checkout; asset caching and server path both matter |
| Algo submission timeout | Could have been accepted; inspect durable session/correlation before retrying |
| App/broker quantities differ | Pause new orders and reconcile positions/trades/external orders |
| Exit partly filled/rejected | Exposure can remain; inspectDhan and explicit Exit & Stop retry |
| Net P&L below last gross row | Fees deducted once; row column is cumulative gross, not independent trade profit |
| Backtest has repeated same-minute reversals | Verify close-confirmed reversal and no earlier-extrema replay rules |

The application logs opening-history diagnostics and surfaces per-stock errors. Avoid logging token-bearing URLs or authentication frames. Runtime state files, journals and customer CSVs are private; they are not suitable documentation attachments.

## 19. Verification and acceptance requirements

The included test inventory is derived from test source declarations. It is **not** a fresh pass report. This documentation task validates documentation/contracts without placing orders, polling account data or rerunning all application integrations. Existing audit reports are historical evidence for their stated snapshot/date only.

Recommended isolated test commands:

```powershell
.\.venv\Scripts\python.exe -m pip install httpx playwright
.\.venv\Scripts\python.exe -m pytest -q
node --test tests/test_dashboard.cjs
```

Python browser tests use Playwright and installedEdge in the existing harness. Reproduce its browser dependency or adapt the harness explicitly for another OS; do not assume the requirements file installs a browser. Use temporary stores and fake broker data. Never run execution integration tests using a customer's real credentials.

### Minimum acceptance matrix for a rebuild

| Area | Required cases |
|---|---|
| Daily ratio | Below/equal/above threshold; high ratio with negative/≤1% exception; >1% fails; no future daily bars |
| Minute volume | Three valid prior samples; exact threshold qualifies; missing/zero/circuit-locked samples handled |
| Turnover | Exactly ₹3 crore fails; one rupee above passes; first close used instead of LTP |
| Candidate | One green candle sufficient; no first-high-break dependency; red/doji excluded |
| Redwala | Red + open=high + turnover; low Vol SMA allowed; missing unrelated history does not block |
| Optional scope | Possible-only filters never leak into Redwala/Retest; five/monthly/two-day filters exempt Redwala |
| Gap/tolerance | Both gap signs; equality limits; either endpoint distance; exact lower tolerance; parent OFF bypass |
| Resistance | Strict swing, age bounds, tie selection, retired level, buffer equality, short listing, unresolved/no_level distinction |
| Badges | First/second PDL strict cross, high/low touch versus break, sticky first-level breaks, 3.5% boundary |
| Ranking | Full Candidate combination first; full Redwala combination second; optional second PDL adds no priority; turnover ties stable |
| Display | Volume strict>; price<=; missing values hidden only when enabled; persistence and invalid drafts |
| CSV | Rupees versus crore headers, signed directions, Top N after classification, duplicates, empty apply, stale preview |
| Preparation | Warm/cold/rollover caches, per-stock interleave, corrupt cache recovery, settings save without history calls, fair scheduler |
| Feed | Late join, reset, disconnect, missing boundary, observed-low-volume bound, historical repair |
| Replay scan | Correct date inputs, snapshot settings, partial warnings, no today's circuit data, entry-cutoff qualification |
| Algo direction | Candidate short override and Redwala long override without changing setup eligibility |
| Sizing/pyramids | Capital flooring; changing add shares; original reference; actual add-fill threshold |
| Reversal | Close accumulated shares/open initial quantity in one delta; counts; target day lock |
| Tick handling | Fast risk touch retained; old generation cannot act on new position; REST does not overwrite fresh depth |
| Orders | Uncertain submission lookup without resend, duplicate trades, partial/rejected exits, mismatch pause |
| Lifecycle | Scanner Stop leaves algos active; restart pauses; duplicate process lock; account change blocked |
| Replay execution | Initial close only; opening extreme once; close-confirmed reversal; no final-bar opposite entry; truncated tail |
| Accounting | Weighted-average realized P&L, cumulative columns, fee once, slippage once, gross minus fees equals net |
| UI integration | Forms survive polling, visible errors, stable filters, stale-result notice, desktop/mobile badge visibility |

## 20. Rebuild sequence and known boundaries

Implement in dependency order:

1. Models, timezone/candle parsing, settings defaults and pure formula tests.
2. Daily/opening/setup-price/resistance/pattern functions with explicit setup scope.
3. Storage, migration, raw-history validation, resolver and CSV import.
4. Broker-data adapter with separate historical/quote scheduling and a fake adapter.
5. Scanner preparation/live-state/confirmation lifecycle, repair and replay.
6. Dashboard forms, badge rendering, exact sorting and display filtering.
7. Fill-driven ladder and replay, with accounting tests before broker execution.
8. Durable intent/session journal, broker reconciliation and mocked failure cases.
9. Independent algo market/order feeds, tick latching, fallback, commands and UI.
10. End-to-end tests in paper/synthetic mode, then deliberate broker compatibility validation.

Do not use a single boolean for both scanner qualification and dashboard visibility. Do not let settings edits mutate an existing algo's risk parameters. Do not make a rejected/missing response indistinguishable from a valid nonqualifier. Do not infer future/live execution from a whole-day backtest badge.

Known boundaries to preserve/document:

- Fixed app F&O list; no automatic membership refresh or derivatives-order implementation.
- Daily/first-minute history may be missing for newly listed/illiquid instruments; required-history filters cannot automatically pass them.
- Saved credentials are plaintext; local deployment is assumed.
- Account-level manual trading in the same instrument/product can cause reconciliation conflicts.
- Exits depend on the application and received prices, with network/broker delays; no guarantee of exact stop price or maximum realized loss.
- Tick observations briefly live in memory before durable worker transfer; a crash in that interval can lose an observation.
- Today's circuit data cannot establish past circuit bands.
- Scanner 60-day and algo 5×366-day limits differ.
- Backtest initial-candle and reversal rules deliberately differ from live execution.
- Tests with fake brokers do not certify current Dhan access, permissions, live liquidity or all API behavior.
- This pack describes code at a specific source manifest; future changes require updating the specification and schema exports.

The repository's README names official Dhan historical data, quote, market feed, orders, order-update and portfolio documentation as integration references. This report describes the pinned implementation; it does not claim a new external documentation-compliance audit. For a new implementation/SDK upgrade, verify those official interfaces and broker requirements before enabling real orders.

## 21. Verified circuit-band display filter

**Implemented in the main project on 8 November 2026.** The previous pending description is superseded by this section.

The control **Only circuit band >=20% - Live** defaults ON. It is a browser-local display filter remembered under `scanner.dashboardCircuit.v 1`. OFF restores otherwise matching rows immediately. It applies to live setup rows, including Possible Candidates, Redwala and Retest; historical backtests and active algos are unaffected.

The backend module `app/circuit_bands.py` verifies both fresh Dhan circuit limits against one reference close. Prefer `last_price - net_change` from the same quote; fall back only to a valid prior close from daily inputs prepared for the current session. An undated previous-close value is not accepted for this verification. Recognize fixed bands 2/5/10/20%, requiring both prices to match. The rounding allowance is at most Rs 0.05, capped at 0.1% of the reference close, plus a tiny numerical allowance. Unrecognized/asymmetric ranges remain unknown rather than rounding up to 20%.

Expose `circuit_reference_close`, `circuit_band_percent`, `circuit_band_status` and `circuit_band_eligible` on the live response model. Statuses are `verified`, `unverified`, `pending_or_stale` and `dynamic`. Eligibility is true only for a recognized verified band >=20%. Known F&O symbols are dynamic using the existing static classification list. This is validation against provider prices, not an independent exchange certification or an automatically refreshed membership classification. Larger unsupported tick-rounding differences remain unverified.

Freshness requires a same-date fetched timestamp between zero and 120 seconds old. Missing/invalid prices, out-of-range LTP, failed quotes or unsupported values cannot produce verified eligibility. A current reference close is not exposed for stale quotes. The dashboard additionally requires the eligible boolean, verified status and finite band >=20 before displaying the row while ON.

The gate runs after setup selection and before the existing volume/price filters and badge/turnover comparator. Both UC Away % and LC Away % remain visible and retain their LTP-based formulas. With reference 100, limits 120/80 and LTP110, the nominal band is 20%, while distances are 9.09% and 27.27%. Those distances are not the filter inputs.

The summary separates lower bands from unverified/dynamic/stale hidden matches; the Qualified Stocks count remains the scanner total. An empty filtered table explains the circuit gate rather than claiming the scanner found no setup. A toggle change rerenders locally and issues no quote/history request.

The circuit worker checks newly eligible stocks every two seconds, while each stock's quote-attempt interval remains 60 seconds and quotes retain the shared 1.05-second throttle. Live data/network latency still determines when verification becomes available. No historical band data is stored, so backtests cannot use today's circuit limits.

Validation:982 Python tests and 46 dashboard JavaScript checks passed, including desktop/mobile browser tests through real FastAPI response serialization and fake Dhan quotes. See `../circuit-band-validation-2026-11-08.md` for scope and limits.

## Documentation provenance

This report was prepared by reading application code, templates, JavaScript, storage, launch scripts, tests and existing project notes in the main workspace. Source paths in companion files are relative so the pack can move between Windows and macOS. `SOURCE_MANIFEST.json` records source hashes, the Git commit reference and a modified-working-tree note. The commit hash alone is not the snapshot identity because the project contains uncommitted changes.

Uploading this report to an AI tool communicates intended behavior and important implementation details. A faithful rebuild still requires implementation and the acceptance checks above; documentation alone cannot establish broker-data equivalence or execution safety.
