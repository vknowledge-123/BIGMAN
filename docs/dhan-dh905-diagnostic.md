# Dhan daily-history rejection: 2026-09-01 backtest

Investigated on 2026-10-12 using a small number of read-only historical requests.
No trading orders were placed. No access tokens or client IDs are included here.

## Reproduction

Daily endpoint: `POST /v2/charts/historical`

```json
{
  "securityId": "27041",
  "exchangeSegment": "NSE_EQ",
  "instrument": "EQUITY",
  "expiryCode": 0,
  "oi": false,
  "fromDate": "2026-06-03",
  "toDate": "2026-09-01"
}
```

| Stock | Security ID | Daily history | Minute history |
|---|---|---|---|
| TBZ | 27041 | DH-905 | Success, 16,152 candles |
| PVRINOX | 13147 | DH-905 | Success, 16,152 candles |
| HFCL | 21954 | DH-905 | Success, 16,152 candles |
| HAPPSTMNDS | From local instrument index | Success, 63 candles | Not tested in this probe |

Minute requests used `2026-07-03 00:00:00` through `2026-09-02 00:00:00`, interval 1 and `oi: false`.

For TBZ, reducing the daily range to August, omitting optional expiry/OI fields, and sending date-time strings also returned DH-905. These were diagnostic probes; production requests retain the documented daily date format.

The documented daily payload matches the application's request. The same format succeeds for HAPPSTMNDS. The exact reason for rejecting daily history for the other securities is not exposed by Dhan's generic error and needs provider investigation.

Reference: [Dhan historical-data documentation](https://dhanhq.co/docs/v2/historical-data/).

## Application handling

- Errors identify daily versus minute history, security ID and requested dates.
- Redwala can still qualify from the completed first candle and turnover alone, but missing daily history is now an explicit partial-result warning.
- Daily-filter-dependent setups and previous-day-low badges cannot be verified from missing daily history. Zero matches in a partial scan is not a complete-universe conclusion.
- Authentication/rate-limit failures stop remaining batch requests, including failures encountered while keeping a valid Redwala result.
- Intraday closing prices are not substituted for official daily closes. That substitution could change daily-volume and opening-price filters.
