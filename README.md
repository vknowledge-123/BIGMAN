# Dhan Turnover Scanner

FastAPI dashboard for scanning NSE stocks by live percent change and latest completed 1-minute candle turnover.

## What It Does

- **Daily Resistance** (default OFF; Possible Candidates only): searches up to 60 completed trading sessions by default for a strict swing high with 2 lower highs before and 2 after. Eligible peak age is 4–60 trading sessions (yesterday = 1). Lookback, both swing counts, age bounds and breakout buffer are configurable. The nearest level at/above the previous close is selected; a subsequent daily close strictly above a peak retires it. Optional minimum pullback checks `(peak high - lowest later daily low) / peak high`; default OFF, value 3%. Equal neighbouring highs do not form a strict swing. Short listing histories are supported; no eligible peak is a resolved rejection, missing/invalid history remains pending.
- With Daily Resistance ON, existing Possible Candidate conditions must pass, then **current live LTP** must be strictly above `resistance * (1 + buffer / 100)`. Qualification can happen after the first minute and disappears while LTP is at/below the threshold; running algos are not stopped by scanner eligibility changes. Replay accepts a **completed green minute candle close** above the threshold and records its completion time. **resistance break** shows that condition. **resistance_break_open** identifies candle 1 or 2 opening strictly below the raw resistance and crossing above the buffered threshold within that candle; live uses its observed high (or repaired historical high), replay requires its close above. A gap above can get the general badge but not the opening-cross badge. Dashboard priority requires the complete badge combinations described below. Redwala and Retest Break are unaffected.
- Enable and **Save & Apply**, then run **Cache Volume + Day Levels** before opening. The daily request expands to cover the requested sessions plus left-side confirmation; raw OHLC and request capacity persist with the session cache. Swing selection is memoized; incoming ticks only compare prices with the selected threshold. Old or undersized caches refresh in preparation/repair, not in the Save request. Backtests build resistance strictly from sessions before their target date; algo replay only sees minute candles completed by its selected entry time. OFF bypasses the feature and its badges. Live ticks and historical candle closes are different evidence and need not produce identical matches. Daily request semantics follow [Dhan historical-data documentation](https://dhanhq.co/docs/v2/historical-data/).
- **Monthly Filter** (default OFF): today's open must be strictly greater than the highest daily close of the previous **20 completed trading sessions**, not calendar days or candle highs.
- **Last 2 Days Filter** (default OFF): when both prior trading-session candles are green (`close > open`), this filter adds no opening condition. If either is red or doji (`close <= open`), today's open must be strictly greater than the highest of those two closes. Equality fails.
- Both new filters apply to **Possible Candidates and Retest Break** in Live and Backtest. **Redwala is exempt from both filters**, including when their daily history is missing. They combine with existing rules; both must pass when enabled together. Opening setups use the first opening candle's open. Backtests use only history before the selected date. Daily-history caches retain 20 dated closes and two dated open/close candles, upgrade older caches when needed, and report incomplete history as unresolved. **Save & Apply** persists the toggles and rechecks cached results without restarting Live. Rerun backtests after saving.
- Saves Dhan `client_id` and `access_token` locally in `data/config.json`.
- Accepts plain NSE trading symbols pasted one per line.
- Also accepts an **NSE Pre-open CSV** directly in the dashboard. Choose **Cash (non-F&O)** or **F&O stocks**, direction (gainers/losers/both), inclusive turnover bounds in crore, signed percentage-change bounds, and optional Top N. Classification uses the same 210-symbol list as the supplied scripts (`app/fno_symbols.py`), not an automatically refreshed exchange list. Filter first, sort by pre-open turnover descending, then apply Top N. F&O mode selects equity stocks, not derivative contracts.
- **Filter CSV** previews without changing the scanner universe. **Use stocks in scanner** replaces the Stocks list, reuses existing scanner caches, and saves the source CSV and import filters in `data/config-preopen.json` for browser/server reloads. Then use **Cache Volume + Day Levels** and **Start Live**. Replacing the universe stops a running scanner feed; active algo sessions remain separate. Invalid uploads and empty matches cannot replace the list. Manual symbol entry is still supported. These import filters are separate from all existing Possible Candidate, Redwala and algo qualification rules.
- CSV handling supports UTF-8/BOM, quoted numbers with Indian grouping, whitespace/newlines in headers, missing numeric values and duplicate symbols. Missing change/turnover rows are counted and skipped; duplicates keep the first valid occurrence. `CHANGE` in rupees is never substituted for `%CHANGE`. Final Price is displayed when available, otherwise IEP/price; missing display prices do not exclude rows. Uploads are limited to 2 MB. Input prices and pre-open turnover are not used to replace Dhan daily or minute candles.
- Resolves symbols to Dhan security IDs from Dhan's scrip master.
- Caches previous day close from Dhan historical daily candles.
- Connects to Dhan Live Market Feed in Quote mode.
- Builds 1-minute candles from live cumulative volume changes.
- Shows latest completed candle turnover as `1m candle volume * candle close`.
- Premarket preparation first checks daily history for every stock, saves the previous close/high/low, and excludes only known daily-filter failures. It fetches the three-session opening-volume average only for survivors. Missing daily data stays unresolved and is retried, never treated as a filter failure.
- Reuses daily and opening-volume caches for the same scan date, including after restarting. On a new date, dated raw samples are reused and missing completed sessions fetched to recompute rolling values. Adding stocks prepares only new or uncached entries. The required opening volume (configured minimum times average) is cached too.
- Preparation retries unresolved entries up to three passes and stops on authentication/rate-limit failures. The dashboard reports prepared, excluded, unresolved, awaiting confirmation and confirmed counts.
- Skips weekends, holidays, missing opening candles, and price-locked opening circuit sessions while finding those three samples.
- Calculates `Volume SMA = today's first candle volume / cached 3-day average`.
- The dashboard's **Volume & Turnover Filters · Live & Backtest** panel independently sets the previous-day maximum ratio, first-minute minimum ratio, and first-candle turnover threshold. Ratios default to `4x`; turnover defaults to `3` crore. All accept positive decimal values and persist across restarts. Enter turnover in crore (e.g. `1.25` = INR `12,500,000`); the API stores `first_candle_turnover_min` in rupees. **Save & Apply** re-evaluates cached daily decisions and confirmed candles without downloading them again, while keeping the active live feed connected. Newly eligible subscriptions and missing opening candles are handled by background workers; repeated edits use the latest settings. The save request performs no Dhan network calls or bulk cache rewrite. The dashboard shows applying/saved feedback, bounds save-response waits to 10 seconds, and allows only one state poll in flight. Prepare newly eligible stocks using **Cache Volume + Day Levels** before opening; incomplete live data falls back to historical confirmation. Rerun backtests after changes; each run retains and displays the settings it started with.
- Optional **Today Open Cross** toggle (default OFF): when ON, Possible Candidates and Retest Break require `first candle open > max(previous 5 trading-session daily closes)`. Equality fails. Redwala is unaffected, including when five-close history is missing. The scanner caches the five dated closes from the existing daily-history response, excluding the scan date and future dates. Backtests use the five sessions before the selected date. Missing five-session history leaves affected setups unresolved, never a pass; older caches are refreshed during preparation/confirmation. Save & Apply rechecks confirmed candles locally; it does not restart the live feed. OFF skips only this condition.
- Possible Candidates and Retest Break require first-minute `Volume SMA >= configured minimum` and the previous-day filter below.
- Also requires first-candle turnover (`first candle volume * first candle close`) strictly greater than the configured threshold (default INR 3 crore / `30,000,000`) for both `Possible candidate` and `redwala gira`, in live and backtest. Equality does not qualify; later candles and live LTP do not determine this filter.
- Marks `Possible candidate` when the first completed opening candle is green and passes both volume checks. No second candle is required; red and doji first candles cannot receive this badge.
- Adds an `open ==low` badge beside `Possible candidate` when the first candle's open equals its low, in both live and backtest results.
- Adds `under_3.5%` to confirmed Possible Candidates when the absolute difference between first-candle open and previous trading-day close is at most 3.5%, including equality. This badge works independently of the Open / Previous Close toggle and its configured limit. It does not change qualification or dashboard priority.
- Marks `redwala gira` when first-candle turnover is strictly above the saved threshold AND the first candle is red with open equal to high. Daily-volume and minute-volume filters do not apply; missing history cannot block this setup. No second candle is required. A stock cannot be both a green-first possible candidate and redwala gira.
- Caches the previous trading session's high and low with the daily filter. Adds `previous day high cross` to possible candidates only when `first open < previous high < first close`. Redwala gira shows `First Candle PDL Cross` only when `first close < previous low < first open`. A separate `PDL Cross on 2nd Candle` badge requires `second close < previous low < second open` on the completed 09:16?09:17 candle, in live and backtest results. Later PDL breaks and intraminute dips alone do not qualify for either badge. Equality/touches do not count. Missing or invalid levels suppress only the corresponding badge. Backtests use the session immediately before the selected date.
- Calculates previous-day daily SMA as the last completed session's volume divided by the average daily volume of its three preceding trading sessions.
- Passes the daily filter when daily SMA is `<= configured maximum` (default `4x`), OR the previous day's signed close-to-close change is `<= +1%`. This includes negative changes; it is not an absolute-percent test.
- Shows previous-day SMA and percent change; hover over the SMA to see dates and volume inputs. Missing or invalid daily data cannot qualify.
- Shows first-candle turnover as a dedicated column in both live and backtest tables.
- Redwala also receives **First Candle Low Break** when a later price is strictly below the first candle low. Touches do not count. Live tick minima and historical minute lows retain this badge after rebounds. Missing PDL suppresses only the **First Candle PDL Cross** badge. All stocks remain subscribed for Redwala, including daily-volume failures; incomplete live data still requires candle confirmation.
- Adds **First Candle High Break** to Possible Candidates after a later observed LTP exceeds the confirmed first high (strictly greater, not a touch). The badge stays for that session after a pullback. Backtests detect the event from later minute highs.
- Adds **Retest Break**: the first candle must be red, followed by an uninterrupted sequence of completed green minute candles until one trades above the first high and closes green. A red/doji before that break rejects the setup; missing minutes remain unresolved. A later red candle does not undo an already confirmed break. No first open = high condition is required. Daily-volume, first-minute volume, first-candle turnover and enabled Today Open Cross filters all apply.
- Live Retest Break confirmation uses Dhan completed history for eligible red-first stocks only, checks new minutes using the shared historical throttle, and stops requesting once confirmed or invalidated. It scans beyond the five displayed candles through the trading session. Quote-feed gaps cannot create a confirmed pattern.
- Use **Show scan** to view All setups, Possible Candidates, Redwala or Retest Break. Live priority group 1 requires **all four**: Possible Candidate, Resistance Break, Resistance Break Open and First Candle High Break. Group 2 requires **all three**: Redwala Gira, First Candle Low Break and First Candle PDL Cross. PDL Cross on 2nd Candle is optional; both three- and four-badge combinations share this priority group, ordered by turnover. All remaining results share group 3, including partial badge combinations and awaiting-confirmation rows. **Each group sorts by first-candle turnover descending**, even with display filters OFF; ties preserve existing order. Open = Low is not required and does not grant priority by itself. First-candle turnover is pinned beside Stock & Badges. The qualified-stock count counts each stock once even if multiple setups match.
- Tracks the first 5 completed opening candles with each candle's turnover, volume, close, colour, and timestamp.
- Seeds opening candles from Dhan intraday history and then adds newly completed candles from the WebSocket feed.
- Orders live results by the complete badge groups described above, then by first-candle turnover within each group.
- Shows setup badges beneath each stock symbol in a pinned column, visible without horizontal scrolling. The five candle turnover cards fit the viewport and wrap on small screens.
- Adds an `F&O` badge for symbols in the configured F&O universe.
- Shows live `UC Away % = (upper circuit - LTP) / LTP * 100` and `LC Away % = (LTP - lower circuit) / LTP * 100` for qualifying stocks, including `redwala gira`. At LTP 100, limits 101/90 mean 1%/10% away.
- **Only circuit band ≥20% · Live** defaults ON. A live row is displayed only when both fresh Dhan circuit prices match a recognized fixed band of at least 20% around the same reference close. The reference is quote `last_price - net_change`, falling back only to valid daily history prepared for the current session. Both limits are checked against standard 2/5/10/20% bands with a small rounding allowance (at most ₹0.05, capped at 0.1% of reference); asymmetric/unrecognized ranges remain unverified. This is validation against Dhan's returned prices, not an independent exchange certification. Known F&O symbols are treated as dynamic and hidden, using the app's existing static classification list. Lower bands, unknown, inconsistent, previous-date and stale quotes are hidden. UC/LC distances remain relative to LTP: reference ₹100, limits ₹120/₹80, LTP ₹110 is a verified 20% band with distances 9.09%/27.27%. Existing badge priority and turnover order remain unchanged. Hidden counts are shown separately from scanner qualification totals. The toggle applies immediately and is remembered in this browser; turning it OFF restores other matches. It does not change scanner qualification, running algos or historical backtests. The worker checks for newly eligible stocks every two seconds while each stock retains its 60-second refresh interval and the shared 1.05-second quote throttle. Historical circuit bands are unavailable, so today's bands are never applied to past dates.
- Fetches limits through Dhan's full quote SDK in batches after candidate checks and every 60 seconds while live. Distances recalculate with LTP updates. Quote requests share a one-request-per-second throttle; failed quotes retry on the next refresh, without affecting badges or eligibility.
- Missing, invalid, previous-date or over-two-minute-old circuit quotes show `--`; a value of 0% means price is at the limit, not necessarily locked there. Circuit prices are not persisted or used in backtests, since historical candles do not include historical circuit bands.
- If Dhan labels the first market candle as `9:14`, the scanner uses that candle as the first candle.
- Provides a manual repair button that fetches missing live 1-minute candles and re-checks the first opening candle.
- Backtests one selected trading date from the last 60 calendar days using Dhan 1-minute historical data.
- Rebuilds each backtest date's three-session opening-volume average instead of using today's cache.


## Selected-stock algo trading and replay

Use **Start Algo** beside a confirmed Possible Candidate or Redwala. The algo panel is below the scanner tables and remains available throughout the trading session. Start is allowed from 09:16 IST until the configured square-off time. Retest Break cannot start an algo.

- Paper is the default on every browser load. Live requires explicitly selecting LIVE and confirming the selected stock, direction and capital. This software requests NSE_EQ INTRADAY MARKET orders; broker acceptance and fills are not guaranteed.
- **First ladder direction**: keep Setup default (Possible Candidate long, Redwala short), or choose Long first / Short first for either setup. The selection applies to paper, live and backtest, and is saved with each session. Setup eligibility remains unchanged. Subsequent reversals still require the ladder toggle.
- Set capital per entry/add, target, stop, optional trailing stop, optional ladder reversals, optional pyramiding and maximum adds. Quantity is rounded down from capital divided by the entry-side quote, without leverage. Each add uses the same capital at its new quote, so share counts can differ. Actual market fills and costs can differ from the estimated capital.
- Target and fixed SL refer to each ladder's original completed entry fill price. In live/paper trading, SL, TSL and target use received LTP updates; TSL follows the best observed LTP and never loosens. Bid/ask are execution estimates, not trigger prices. Adds occur at SL-percent intervals from the last add's average fill. A reversal closes all accumulated shares and opens the original initial share quantity in the opposite direction, using one order for the combined quantity. Target exits lock that stock/mode/account for the day.
- Maximum reversals, maximum session loss and scheduled square-off also apply. Loss limits trigger an exit; gaps, liquidity, disconnections and fees can cause a larger loss. Use Exit & Stop to cancel pending remainders, reconcile fills and flatten actual app-owned exposure. A rejected or partially filled exit pauses for explicit retry instead of looping orders.
- Save Algo Defaults affects new sessions only. Existing sessions retain an immutable settings snapshot. Scanner Stop does not stop algos. Monitor the separate session cards, broker quantity, fills, status and pending orders.
- Algo Backtest accepts a symbol, setup, historical trading date and entry time. It rechecks eligibility using saved scanner filters and only information completed before entry. Historical replay is always paper, even with LIVE selected. **Backtests check the initial entry candle only at its close**: its high/low do not trigger exits, adds, or trailing watermark changes, regardless of candle colour. Close-triggered fills use the close plus slippage and carry the candle-end timestamp. From the next candle, OHLC checks apply. **Backtests alone confirm ladder reversals at candle close**: the close must be at or beyond the current SL/TSL. The combined reversal fills at that close plus slippage and is timestamped at candle end; the new position is first evaluated in the following candle. Intraminute stop touches that recover before close do not reverse. After the entry candle, targets, adds, maximum-loss exits, and stops that cannot reverse retain their OHLC execution rules. No opposite position opens at square-off or at the end of available data. Live/paper execution continues to reverse immediately, so backtest results intentionally use different reversal timing. It uses minute OHLC: when open equals high or low, that opening extreme is consumed first without inventing a later revisit; the recorded close can still cause a rebound. Other candles retain the adverse-extreme-first assumption. Exact intraminute chronology is unavailable: intraminute fill times identify the candle, while close-confirmed reversals use candle-end timestamps. Slippage and per-order costs are configurable. These costs are estimates, not a brokerage/tax calculation. Missing interior minutes fail the replay; shortened sessions are labelled incomplete and closed at the last available candle. Availability is limited by Dhan history and the currently resolvable instrument universe (not a survivorship-free universe).

Execution state and order intents are stored in `data/algo.sqlite3` with an exclusive process lock. Run one server process, without reload or multiple workers, for execution. Restarted sessions pause until Reconcile & Resume. An uncertain order submission is looked up by its correlation ID and is never automatically resent. Duplicate/out-of-order socket notifications only wake REST reconciliation; trade IDs determine actual fills. A quantity mismatch or external pending intraday order blocks new submissions. Do not manually trade the same stock/product while its algo runs.

**Exits are application-managed, not broker-hosted protective orders.** Keep the server and network running. A dedicated selected-stock Full market websocket supplies LTP and five-level depth independently of Scanner Start/Stop. Every accepted fresh LTP is evaluated locally, including while the order worker waits for REST. Exit/reversal signals are latched so a brief touch is not erased by a recovery. Stale, invalid and older-timestamp packets are ignored. Signals and risk watermarks are transferred to the durable session by the execution worker; a process crash before that transfer can still lose an in-memory tick.

Cached fresh bid/ask normally avoids an extra quote request. A separate fallback worker requests only stocks with missing/stale market data, using the existing shared 1.05-second quote throttle. It does not block tick reception or order processing. Entry/add sizing uses current depth; market orders do not guarantee that price. A triggered live flatten can proceed without depth after broker checks; paper fills and new exposure wait for fresh bid/ask. An unavailable order socket blocks entries/adds/reversals. Market/order socket indicators and session messages show connection/fallback state.

Orders remain serialized, with broker position/order checks before submissions. The order-update socket wakes REST reconciliation; only verified trades change quantity. Partial-fill risk touches request cancellation, then flatten actual reconciled exposure. Ticks from an old fill generation cannot trigger the newly filled ladder. Broker/API round trips and other pending sessions still add latency; this is not an instantaneous or exchange-hosted stop. If both websocket and REST data fail, price exits cannot detect new touches. A pending order that cannot be cancelled or reconciled requires checking Dhan. Before stopping the server, exit each session and verify the broker is flat. Live execution needs valid Dhan credentials, trading permissions, sufficient margin and static-IP whitelisting.

Implementation references: [Dhan orders](https://dhanhq.co/docs/v2/orders/), [order updates](https://dhanhq.co/docs/v2/order-update/), [positions](https://dhanhq.co/docs/v2/portfolio/), [quotes](https://dhanhq.co/docs/v2/market-quote/), [market websocket](https://dhanhq.co/docs/v2/live-market-feed/). SDK order endpoints are used; the order socket uses the documented protocol directly to avoid SDK 2.2.0's authentication-frame logging.

Validation uses fake broker responses and quotes; no real orders are placed by the tests. Run `py -m pytest -q`. The browser test additionally requires Python Playwright and installed Edge; it intercepts all application requests and calls isolated FastAPI handlers. See `tests/test_algo.py` and `tests/test_algo_browser.py`.

## Install

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

If you do not use a virtual environment:

```powershell
py -m pip install -r requirements.txt
```

## Run

On Windows, double-click **Start Scanner.bat** in the project folder. It uses `.venv` or `venv` when present, otherwise the installed Python, starts one server and opens the dashboard when ready. Keep its window open while scanning or running algos. You can create a desktop shortcut to the batch file; do not move the file out of the project folder. If a healthy app is already on port 8000, the launcher opens that dashboard instead of starting a duplicate. If that port is occupied by an unresponsive server, it reports the problem and leaves the existing process alone. Missing dependencies are reported with the exact one-time installation command.

The double-click launcher runs without auto-reload. Finish/exit active algos in the dashboard before pressing Ctrl+C in its window to close the app.

For development with automatic reload:

```powershell
py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or start it in the background:

```powershell
.\scripts\start_dev_server.ps1
```

Stop the background server:

```powershell
.\scripts\stop_dev_server.ps1
```

Open:

```text
http://127.0.0.1:8000
```

## Dashboard Flow

1. Enter Dhan Client ID and Access Token, then click `Save`.
2. Paste symbols and click `Save List`.
3. Click `Cache Close` to fetch previous close.
4. Click `Cache Volume + Day Levels` before market open. For each stock this applies the daily filter and immediately prepares its opening average if it passes; other stocks do not have to finish their daily checks first. Repeating it reuses today's valid data and retries unresolved entries. Daily history also supplies the previous close, so a separate `Cache Close` request is not required for prepared stocks.
5. Click `Start Live` before 9:15 IST. All stocks are subscribed, including daily-filter failures needed for turnover-only Redwala. At 9:16 a timer screens observed opening candles locally, without waiting for another trade. Live-derived matches appear as `Awaiting confirmation`; final badges and confirmed counts use Dhan historical candles. Likely matches are confirmed first, then incomplete/uncertain observations. Confirmed and safely rejected stocks are skipped on subsequent passes. Unresolved stocks keep retrying until stopped or 15:31 IST, with per-stock backoff up to 30 seconds; authentication/rate-limit failures stop the batch. A busy preparation stock is skipped for that pass instead of downloading its history twice. Results appear progressively through the dashboard's two-second refresh. Finishing within 5-10 seconds depends on list size, feed coverage and API latency; it is not guaranteed.
6. Saving a changed stock list while live stops the old subscription; prepare the updated list and click `Start Live` again.
7. Use `Repair + Check Open` if some 1-minute candles are missing due to feed interruption, or to manually refresh candidate checks.

## Opening scan and request priority

- Live observation uses premarket cumulative-volume baselines, opening timestamps, a boundary quote, and disconnect/reset checks. Premarket quotes seed volume but never create a fake 9:14 candle.
- Only a safely bounded low-volume observation is rejected without REST: cumulative volume through the first boundary quote, minus the premarket baseline, is already below the configured first-minute threshold. That bound includes any early second-minute trades, so sparse quote updates cannot hide an opening-volume qualifier. Missing baselines, late joins, delayed frames, resets and disconnects require historical confirmation. Apparent turnover/colour failures are also confirmed when sampled OHLC cannot establish the true first candle.
- Confirmation requests receive priority in the shared historical request scheduler. After three priority requests, a waiting background request gets a turn; idle priority workers do not reserve the scheduler. An already-running request is allowed to finish. The 0.23-second history throttle, quote throttle and retry backoff remain in effect. Circuit limits refresh on a separate worker during automatic confirmation.
- Historical caches live in `data/config-cache.sqlite3`, separate from credentials/settings in `data/config.json`. Existing JSON caches migrate automatically in a transaction before their old JSON fields are removed. Prepared snapshots are keyed by stock/session; raw daily and opening history is keyed by instrument ID/segment/type. Memory state is published immediately; prepared snapshots flush in batches of up to 25 stocks or after two seconds of ongoing work, with a final flush on completion/error. Newer snapshots cannot be overwritten by an older delayed batch.
- Daily history refreshes the last known completed bar plus newer sessions. Opening history retains dated opening samples and prior closes; rollover fetches the missing date range. Empty deltas trigger a broader recheck, malformed samples refetch, and old/future data cannot qualify a different scan date without recomputation. Backtests only use sessions before their target date.
- When a narrow opening-history response lacks 09:14/09:15, confirmation tries one wider window from the preceding calendar day to now. Later retries use that recovery window directly. Counts, returned timestamp bounds and request windows are logged and saved in SQLite's `history` table under `opening_diagnostic`. Missing data remains unresolved, never a confirmed signal.
- SQLite uses Python's built-in module; no extra installation is needed. To back up caches, stop the app and copy the database with the rest of `data`. Credentials remain in the separate JSON file and should not be shared with clients.
- Preparation caches do not cache live or backtest qualification decisions. Historical backtests still rebuild their own date-relative data and do not use today's premarket exclusions or live previews.

## Backtest Flow

Run Backtest first saves the current filter controls, including all three toggles, then starts the scan. If validation or saving fails, the backtest does not start. Unapplied edits are labelled beside the saved settings; existing results retain the filters used for that run. Saving also applies the selections to Live.

1. Save Dhan credentials and the stock list.
2. Open the `Backtest` tab.
3. Select one date from the last 60 days and click `Run Backtest`.
4. Review stocks passing both volume checks and the candle rules, including their first candle colour, opening average, previous-day SMA/percent change, setup badge, and F&O badge.

Backtesting does not require `Cache Close`, `Cache Volume + Day Levels`, or `Start Live`. Both volume checks are rebuilt relative to the selected date, without using subsequent sessions. Daily history uses actual returned trading sessions, not calendar-day subtraction. Daily and minute history share a 0.23-second minimum request spacing (about 4.35 requests/second maximum), without extra per-stock sleeps. OHLC and full quotes retain a separate 1.05-second spacing and existing retry backoff. Large lists and retries take longer.

## Notes

- The app is configured for NSE equity symbols and Dhan `NSE_EQ` / `EQUITY`.
- Dhan's WebSocket feed needs Live Market Feed/Data API access on your Dhan account.
- Dhan access tokens expire. Save a fresh token if the dashboard reports `DH-901`.
- Your access token is stored as plain local JSON in `data/config.json`; keep this folder private.
- On the first live tick for a stock, volume delta is seeded from the current Dhan day-volume value, so turnover starts counting accurately after that tick instead of showing the full day volume as a fake 1-minute candle.

## Tests

Integration tests exercise the real API, scanner and temporary-file storage with a simulated Dhan SDK. They do not use saved credentials or send broker requests. The browser integration cases use installed Microsoft Edge and route the dashboard through the real FastAPI test client; no running app server is required.

```powershell
py -m pip install httpx playwright
py -m pytest -q
py -m pytest tests/test_integration_workflows.py -q
node --test tests/test_dashboard.cjs
```

The integration suite covers cache preparation, saved settings and restart, Redwala history recovery, stale-volume protection, unfinished/malformed candles, failed feed startup, stop during in-flight history, removal of the retired Premarket Setup endpoints, and desktop/mobile dashboard workflows.

Optional desktop/mobile browser checks use Edge and mocked API responses (no Dhan requests). Start the app on port 8011, then:

```powershell
npm install --prefix "$env:TEMP/gapfilter-browser-tests" --no-save --no-package-lock playwright
$env:PLAYWRIGHT_MODULE = "$env:TEMP/gapfilter-browser-tests/node_modules/playwright"
node tests/test_dashboard_browser.cjs
```

Set `APP_URL` for another port. Screenshots go to the temporary `gapfilter-browser-artifacts` directory.


Integration audit (17 October 2026): [tested workflows, Dhan contract fixes and limitations](docs/integration-audit-2026-10-17.md). Algo backtest results now separate gross P&L, costs and net P&L, and display a rerun notice after input changes.

Scanner price filters (23 October 2026): both toggles default OFF. **Redwala Open or Close / Previous Close** requires `first close < previous close < first open` and either `abs(first open - previous close) / previous close * 100 <= limit` OR `abs(first close - previous close) / previous close * 100 <= limit` (default 1%). Only one of the two distances needs to satisfy the limit. **Redwala Opening tolerance band** defaults OFF with a 0.5% limit. When both this toggle and the parent Redwala price filter are ON, replace the strict opening condition with `(first open - previous close) / previous close * 100 >= -tolerance`. An opening equal to the previous close is allowed, as is an opening exactly at the lower tolerance boundary. The close must still be strictly below the previous close and the separate open-or-close distance limit still applies. With previous close 200 and tolerance 0.5%, open 199 is allowed and 198.99 is rejected. Disabling the parent filter also skips the tolerance condition; Possible Candidates and Retest Break are unaffected. The same rule applies to live previews, confirmed results, scanner backtests and algo backtest qualification. It adds to Redwala's existing turnover, red candle and open-equals-high rules; volume filters remain excluded. **PDHL** applies only to Possible Candidates, requiring `(previous high - previous low) / previous low * 100 <= maximum range` (default 4%). Retest Break is unaffected by either toggle. Limits accept nonnegative decimal percentages, including equality. Cached levels must belong to the scan session; missing required levels remain unresolved and are refreshed in the background. Save & Apply recalculates cached live results without network requests; rerun scanner/algo backtests to apply new settings. Active algo sessions keep their execution settings.

Live and Backtest display filter: **Filter dashboard by first-candle volume** defaults OFF, with a threshold of 100,000 shares. When ON, only matching setups with first-candle volume strictly above the threshold are displayed, including Redwala; equality and missing volume are hidden. Existing breakout-badge priority is retained, and each group is sorted by first-candle turnover descending. Changes apply locally immediately without API requests, restarting feeds or changing scanner qualification or active algos. Existing backtest rows are filtered immediately. The threshold accepts nonnegative whole shares; invalid drafts keep the last valid threshold. Preferences are stored in this browser when local storage is available. The display summary reports visible/hidden counts; Qualified Stocks remains the scanner total.

**Open / Previous Close - Possible Candidates only** defaults OFF with a 1% limit. When ON, `abs(first candle open - previous trading-day close) / previous close * 100 <= limit` is required. Both gap-up and gap-down openings are checked, including equality; with previous close 200 and limit 1%, opens from 198 to 202 pass. Redwala and Retest Break are unaffected. The setting is saved with scanner filters and used for live previews/confirmation, scanner backtests and algo backtest qualification. It combines with PDHL and other enabled conditions. Missing or stale previous-close history remains unresolved and uses the existing cache/repair workflow. Save & Apply updates cached results; rerun backtests for new settings.

Display filters now apply to both Live and Backtest tables and are visible above both tabs. Absolute volume uses live `today_opening_volume` or backtest `first_candle_volume`; price (OFF by default, Rs250) uses live LTP or backtest `first_candle_close`. Volume must be strictly greater than its threshold; stock price must be at or below its maximum (equality included). Both exclude missing values when enabled and combine with the setup selector. Preferences are local to this browser. Filtering re-renders existing results immediately without changing scanner totals or active algos. Backtest rows now expose first open, first close, previous close and absolute opening gap, separate from the previous-day percentage change. A warning identifies results generated with different scanner settings; rerun to apply changed qualification filters. Requested opening-gap settings are checked against the returned backtest settings before new results are displayed.

Integration audit (31 October 2026): [fixes, tested workflows and verification limits](docs/integration-audit-2026-10-31.md). Scanner backtests now carry their selected settings with the request to prevent another tab from changing the run. Manual stock-list saves preserve the existing list if instrument lookup fails. Date inputs and candle labels use IST.

NSE CSV turnover units: detailed exports containing FINAL PRICE, FINAL VOLUME and bare VALUE (or TOTAL VALUE / TURNOVER) are read as rupees and divided by 10,000,000 before display, filtering and sorting. Explicit crore-labelled columns retain their values; explicit VALUE (INR), VALUE (RS), VALUE (RUPEES) and rupee-symbol headers are also supported. The preview states the interpreted unit and applied minimum/maximum in crore. Existing saved CSVs are normalized again on preview; click Use stocks in scanner to replace a list previously selected using incorrect units.
