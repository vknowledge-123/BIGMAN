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
- Sorts rows by `% change` first, then `1m turnover`.
- Marks `Possible candidate` when Dhan intraday opening candles are opposite colors: `green + red` or `red + green`. If Dhan labels the first market candle as `9:14`, it also tries the `9:14/9:15` pair.
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
3. Click `Cache Data` to fetch previous close.
4. `Cache Data` also checks the official Dhan intraday opening candles for the candidate badge.
5. Click `Start Live` to connect the WebSocket feed.
6. Use `Repair + Check Open` if some 1-minute candles are missing due to feed interruption, or if you started after market open and want to re-check candidate badges.

## Notes

- The app is configured for NSE equity symbols and Dhan `NSE_EQ` / `EQUITY`.
- Dhan's WebSocket feed needs Live Market Feed/Data API access on your Dhan account.
- Your access token is stored as plain local JSON in `data/config.json`; keep this folder private.
- On the first live tick for a stock, volume delta is seeded from the current Dhan day-volume value, so turnover starts counting accurately after that tick instead of showing the full day volume as a fake 1-minute candle.
