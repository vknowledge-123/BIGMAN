# Dhan Turnover Scanner

FastAPI dashboard for scanning NSE stocks by live percent change and latest completed 1-minute candle turnover.

## What It Does

- Saves Dhan `client_id` and `access_token` locally in `data/config.json`.
- Accepts plain NSE trading symbols pasted one per line.
- Resolves symbols to Dhan security IDs from Dhan's scrip master.
- Caches previous day close from Dhan historical daily candles.
- Connects to Dhan Live Market Feed in Quote mode.
- Builds 1-minute candles from live cumulative volume changes.
- Shows latest completed candle turnover as `1m candle volume * candle close`.
- Caches the first 1-minute candle volume from the latest three valid prior trading days and calculates their average.
- Skips weekends, holidays, missing opening candles, and price-locked opening circuit sessions while finding those three samples.
- Calculates `Volume SMA = today's first candle volume / cached 3-day average`.
- Requires first-minute `Volume SMA >= 4.00x` and the previous-day filter below for every displayed stock.
- Marks `Possible candidate` for `green + green`, `green + red`, or `red + green` opening candles passing both volume checks.
- Marks `redwala gira` when both volume checks pass AND the first candle is red with open equal to high. The second candle can have any colour or be unavailable. A red/green pair can receive both setup badges. `Possible candidate` still requires its two-candle colour pattern; doji pairs cannot receive that badge.
- Calculates previous-day daily SMA as the last completed session's volume divided by the average daily volume of its three preceding trading sessions.
- Passes the daily filter when daily SMA is `<= 4x`, OR the previous day's signed close-to-close change is `<= +1%`. This includes negative changes; it is not an absolute-percent test.
- Shows previous-day SMA and percent change; hover over the SMA to see dates and volume inputs. Missing or invalid daily data cannot qualify.
- Shows the first and second opening-candle colours and the first-candle turnover in live mode.
- Tracks the first 10 completed opening candles with each candle's turnover, volume, close, colour, and timestamp.
- Seeds opening candles from Dhan intraday history and then adds newly completed candles from the WebSocket feed.
- Pins possible candidates first, then sorts by `% change` and `1m turnover`.
- Adds an `F&O` badge for symbols in the configured F&O universe.
- Shows live `UC Away % = (upper circuit - LTP) / LTP * 100` and `LC Away % = (LTP - lower circuit) / LTP * 100` for qualifying stocks, including `redwala gira`. At LTP 100, limits 101/90 mean 1%/10% away.
- Fetches limits through Dhan's full quote SDK in batches after candidate checks and every 60 seconds while live. Distances recalculate with LTP updates. Quote requests share a one-request-per-second throttle; failed quotes retry on the next refresh, without affecting badges or eligibility.
- Missing, invalid, previous-date or over-two-minute-old circuit quotes show `--`; a value of 0% means price is at the limit, not necessarily locked there. Circuit prices are not persisted or used in backtests, since historical candles do not include historical circuit bands.
- If Dhan labels the first market candle as `9:14`, the scanner uses the `9:14/9:15` pair.
- Provides a manual repair button that fetches missing live 1-minute candles and re-checks the 9:15/9:16 candidate candles.
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
4. Click `Cache Volume Average` to cache three valid prior opening volumes and the previous-day daily filter. Refresh this each scan day. You can run it before, during, or after market hours.
5. Click `Start Live` to connect the WebSocket feed. At 9:16 IST the app starts confirming the completed first candle from Dhan intraday data for `redwala gira`, then checks both opening candles at 9:17 IST for `Possible candidate`. Actual results depend on API availability and processing time.
6. Use `Repair + Check Open` if some 1-minute candles are missing due to feed interruption, or to manually refresh candidate checks.

## Backtest Flow

1. Save Dhan credentials and the stock list.
2. Open the `Backtest` tab.
3. Select one date from the last 60 days and click `Run Backtest`.
4. Review stocks passing both volume checks and the candle rules, including their first two candle colours, opening average, previous-day SMA/percent change, setup badge, and F&O badge.

Backtesting does not require `Cache Close`, `Cache Volume Average`, or `Start Live`. Both volume checks are rebuilt relative to the selected date, without using subsequent sessions. Daily history uses actual returned trading sessions, not calendar-day subtraction. Requests are throttled; large lists and retries take longer.

## Notes

- The app is configured for NSE equity symbols and Dhan `NSE_EQ` / `EQUITY`.
- Dhan's WebSocket feed needs Live Market Feed/Data API access on your Dhan account.
- Dhan access tokens expire. Save a fresh token if the dashboard reports `DH-901`.
- Your access token is stored as plain local JSON in `data/config.json`; keep this folder private.
- On the first live tick for a stock, volume delta is seeded from the current Dhan day-volume value, so turnover starts counting accurately after that tick instead of showing the full day volume as a fake 1-minute candle.

## Tests

```powershell
py -m pytest -q
node --test tests/test_dashboard.cjs
```

Optional desktop/mobile browser checks use Edge and mocked API responses (no Dhan requests). Start the app on port 8011, then:

```powershell
npm install --prefix "$env:TEMP/gapfilter-browser-tests" --no-save --no-package-lock playwright
$env:PLAYWRIGHT_MODULE = "$env:TEMP/gapfilter-browser-tests/node_modules/playwright"
node tests/test_dashboard_browser.cjs
```

Set `APP_URL` for another port. Screenshots go to the temporary `gapfilter-browser-artifacts` directory.
