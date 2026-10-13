# Dhan Turnover Scanner

FastAPI dashboard for scanning NSE stocks by live percent change and latest completed 1-minute candle turnover.

## What It Does

- **Monthly Filter** (default OFF): today's open must be strictly greater than the highest daily close of the previous **20 completed trading sessions**, not calendar days or candle highs.
- **Last 2 Days Filter** (default OFF): when both prior trading-session candles are green (`close > open`), this filter adds no opening condition. If either is red or doji (`close <= open`), today's open must be strictly greater than the highest of those two closes. Equality fails.
- Both new filters apply to **Possible Candidates and Retest Break** in Live and Backtest. **Redwala is exempt from both filters**, including when their daily history is missing. They combine with existing rules; both must pass when enabled together. Opening setups use the first opening candle's open. Backtests use only history before the selected date. Daily-history caches retain 20 dated closes and two dated open/close candles, upgrade older caches when needed, and report incomplete history as unresolved. **Save & Apply** persists the toggles and rechecks cached results without restarting Live. Rerun backtests after saving.
- Saves Dhan `client_id` and `access_token` locally in `data/config.json`.
- Accepts plain NSE trading symbols pasted one per line.
- Resolves symbols to Dhan security IDs from Dhan's scrip master.
- Caches previous day close from Dhan historical daily candles.
- Connects to Dhan Live Market Feed in Quote mode.
- Builds 1-minute candles from live cumulative volume changes.
- Shows latest completed candle turnover as `1m candle volume * candle close`.
- Premarket preparation first checks daily history for every stock, saves the previous close/high/low, and excludes only known daily-filter failures. It fetches the three-session opening-volume average only for survivors. Missing daily data stays unresolved and is retried, never treated as a filter failure.
- Reuses daily and opening-volume caches for the same scan date, including after restarting; a new date invalidates them. Adding stocks prepares only new or uncached entries. The required opening volume (configured minimum times average) is cached too.
- Preparation retries unresolved entries up to three passes and stops on authentication/rate-limit failures. The dashboard reports prepared, excluded, unresolved, awaiting confirmation and confirmed counts.
- Skips weekends, holidays, missing opening candles, and price-locked opening circuit sessions while finding those three samples.
- Calculates `Volume SMA = today's first candle volume / cached 3-day average`.
- The dashboard's **Volume & Turnover Filters · Live & Backtest** panel independently sets the previous-day maximum ratio, first-minute minimum ratio, and first-candle turnover threshold. Ratios default to `4x`; turnover defaults to `3` crore. All accept positive decimal values and persist across restarts. Enter turnover in crore (e.g. `1.25` = INR `12,500,000`); the API stores `first_candle_turnover_min` in rupees. **Save & Apply** re-evaluates cached daily decisions and confirmed candles without downloading them again, while keeping the active live feed connected. Newly eligible subscriptions and missing opening candles are handled by background workers; repeated edits use the latest settings. The save request performs no Dhan network calls or bulk cache rewrite. The dashboard shows applying/saved feedback, bounds save-response waits to 10 seconds, and allows only one state poll in flight. Prepare newly eligible stocks using **Cache Volume + Day Levels** before opening; incomplete live data falls back to historical confirmation. Rerun backtests after changes; each run retains and displays the settings it started with.
- Optional **Today Open Cross** toggle (default OFF): when ON, Possible Candidates and Retest Break require `first candle open > max(previous 5 trading-session daily closes)`. Equality fails. Redwala is unaffected, including when five-close history is missing. The scanner caches the five dated closes from the existing daily-history response, excluding the scan date and future dates. Backtests use the five sessions before the selected date. Missing five-session history leaves affected setups unresolved, never a pass; older caches are refreshed during preparation/confirmation. Save & Apply rechecks confirmed candles locally; it does not restart the live feed. OFF skips only this condition.
- Possible Candidates and Retest Break require first-minute `Volume SMA >= configured minimum` and the previous-day filter below.
- Also requires first-candle turnover (`first candle volume * first candle close`) strictly greater than the configured threshold (default INR 3 crore / `30,000,000`) for both `Possible candidate` and `redwala gira`, in live and backtest. Equality does not qualify; later candles and live LTP do not determine this filter.
- Marks `Possible candidate` when the first completed opening candle is green and passes both volume checks. No second candle is required; red and doji first candles cannot receive this badge.
- Adds an `open ==low` badge beside `Possible candidate` when the first candle's open equals its low, in both live and backtest results.
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
- Use **Show scan** to view All setups, Possible Candidates, Redwala or Retest Break. Live results prioritize Possible Candidates and Redwala carrying first-candle high/low break or previous-day high/low cross badges, preserving existing order within each group. Other matches remain below. First-candle turnover is pinned beside Stock & Badges. The qualified-stock count counts each stock once even if multiple setups match.
- Tracks the first 5 completed opening candles with each candle's turnover, volume, close, colour, and timestamp.
- Seeds opening candles from Dhan intraday history and then adds newly completed candles from the WebSocket feed.
- Pins possible candidates first, then sorts by `% change` and `1m turnover`.
- Shows setup badges beneath each stock symbol in a pinned column, visible without horizontal scrolling. The five candle turnover cards fit the viewport and wrap on small screens.
- Adds an `F&O` badge for symbols in the configured F&O universe.
- Shows live `UC Away % = (upper circuit - LTP) / LTP * 100` and `LC Away % = (LTP - lower circuit) / LTP * 100` for qualifying stocks, including `redwala gira`. At LTP 100, limits 101/90 mean 1%/10% away.
- Fetches limits through Dhan's full quote SDK in batches after candidate checks and every 60 seconds while live. Distances recalculate with LTP updates. Quote requests share a one-request-per-second throttle; failed quotes retry on the next refresh, without affecting badges or eligibility.
- Missing, invalid, previous-date or over-two-minute-old circuit quotes show `--`; a value of 0% means price is at the limit, not necessarily locked there. Circuit prices are not persisted or used in backtests, since historical candles do not include historical circuit bands.
- If Dhan labels the first market candle as `9:14`, the scanner uses that candle as the first candle.
- Provides a manual repair button that fetches missing live 1-minute candles and re-checks the first opening candle.
- Backtests one selected trading date from the last 60 calendar days using Dhan 1-minute historical data.
- Rebuilds each backtest date's three-session opening-volume average instead of using today's cache.

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
4. Click `Cache Volume + Day Levels` before market open. This first applies the daily filter to the whole list, then fetches opening averages only for survivors. Repeating it reuses today's valid data and retries unresolved entries. Daily history also supplies the previous close, so a separate `Cache Close` request is not required for prepared stocks.
5. Click `Start Live` before 9:15 IST. Only daily-filter survivors and unresolved stocks are subscribed. At 9:16 a timer screens observed opening candles locally, without waiting for another trade. Live-derived matches appear as `Awaiting confirmation`; final badges and confirmed counts use Dhan historical candles. Likely matches are confirmed first, then incomplete/uncertain observations. Confirmed and safely rejected stocks are skipped on subsequent passes. Unresolved confirmation requests retry up to five more passes with two-second gaps. Results appear progressively through the dashboard's two-second refresh. Finishing within 5-10 seconds depends on list size, feed coverage and API latency; it is not guaranteed.
6. Saving a changed stock list while live stops the old subscription; prepare the updated list and click `Start Live` again.
7. Use `Repair + Check Open` if some 1-minute candles are missing due to feed interruption, or to manually refresh candidate checks.

## Opening scan and request priority

- Live observation uses premarket cumulative-volume baselines, opening timestamps, a boundary quote, and disconnect/reset checks. Premarket quotes seed volume but never create a fake 9:14 candle.
- Only a safely bounded low-volume observation is rejected without REST: cumulative volume through the first boundary quote, minus the premarket baseline, is already below the configured first-minute threshold. That bound includes any early second-minute trades, so sparse quote updates cannot hide an opening-volume qualifier. Missing baselines, late joins, delayed frames, resets and disconnects require historical confirmation. Apparent turnover/colour failures are also confirmed when sampled OHLC cannot establish the true first candle.
- Confirmation requests reserve the shared historical request scheduler ahead of backtests and cache jobs. An already-running request is allowed to finish. The 0.23-second history throttle, quote throttle and retry backoff remain in effect. Circuit limits refresh on a separate worker during automatic confirmation.
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
