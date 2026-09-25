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
- Keeps only stocks with a `Volume SMA >= 4.00x` in the dashboard table.
- Marks `Possible candidate` only when volume is at least `4.00x` and the two opening candles have opposite colors: `green + red` or `red + green`.
- Pins possible candidates first, then sorts by `% change` and `1m turnover`.
- Adds an `F&O` badge for symbols in the configured F&O universe.
- If Dhan labels the first market candle as `9:14`, the scanner uses the `9:14/9:15` pair.
- Provides a manual repair button that fetches missing live 1-minute candles and re-checks the 9:15/9:16 candidate candles.

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
4. Click `Cache Volume Average` to cache three valid prior opening volumes. You can run this before, during, or after market hours.
5. Click `Start Live` to connect the WebSocket feed. At 9:17 IST the app automatically confirms today's opening candles from Dhan intraday data.
6. Use `Repair + Check Open` if some 1-minute candles are missing due to feed interruption, or to manually refresh candidate checks.

## Notes

- The app is configured for NSE equity symbols and Dhan `NSE_EQ` / `EQUITY`.
- Dhan's WebSocket feed needs Live Market Feed/Data API access on your Dhan account.
- Dhan access tokens expire. Save a fresh token if the dashboard reports `DH-901`.
- Your access token is stored as plain local JSON in `data/config.json`; keep this folder private.
- On the first live tick for a stock, volume delta is seeded from the current Dhan day-volume value, so turnover starts counting accurately after that tick instead of showing the full day volume as a fake 1-minute candle.
