# Cache pipeline validation — 2026-11-05

Implemented in E:/BIGMAN-main/BIGMAN-main after testing in an isolated checkout.

## Changes

- SQLite stores prepared snapshots by stock/session and dated history by instrument. Credentials and settings remain in JSON. Migration commits the database before removing historical JSON fields.
- Prepared data is available in memory immediately. Prepared snapshots flush in batches of up to 25 stocks or after two seconds during ongoing work, plus a final flush. Older delayed batches cannot overwrite newer snapshots.
- Each eligible stock gets daily and opening-volume preparation together. Per-stock locks avoid duplicate work between preparation and confirmation.
- Dated daily/opening samples roll forward. Empty or stale deltas trigger broader rechecks; malformed caches refetch. Backtests exclude their target date and future bars.
- Confirmation has request priority, with one background slot after three priority requests when background work is waiting. History spacing remains 0.23 seconds; quote spacing remains 1.05 seconds, with existing retry backoff.
- Missing opening candles trigger a wider recovery window. Counts, timestamp bounds and request windows are saved as opening_diagnostic records. Unresolved confirmation retries with backoff up to 30 seconds until stopped or 15:31 IST, subject to fatal broker errors. Completed stocks are skipped.

## Validation

- **950 Python checks passed** in 75.17 seconds, including API, storage, browser, scanner, resistance, backtest and algo regressions.
- **42 dashboard JavaScript checks passed.**
- Added 18 cache/pipeline tests covering migration failure recovery, concurrent stores, stale snapshots, 266-stock batching, sample rollover, invalid/future data, recovery diagnostics, continued retries, stock locks and scheduling fairness.
- Tests used simulated broker boundaries; no real orders were placed.
- Diff whitespace checks passed.

## Local storage benchmark

Synthetic 2,442-stock cache, each with 62 daily bars:

| Measurement | Result |
|---|---:|
| Legacy JSON | 31.92 MB |
| Settings JSON after migration | 3,429 bytes |
| One-time migration | 1.229 seconds |
| Median single-stock update | 2.568 milliseconds |
| Batched persistence of 266 records | 0.066 seconds |

These measure storage only, not broker or network latency.

## Running-app verification

No algo sessions were active. The scanner was stopped before applying files. The old worker hung while closing its websocket and blocked reload; that stopped worker was terminated so the existing supervisor could start the update.

Migration retained **2,442 prepared stock records**. Actual settings JSON shrank from **14,412,566 to 5,455 bytes**. All **266 symbols** loaded and the scanner reconnected. All 266 recorded opening-history responses contained an opening candle. Confirmation completed for 260 stocks, producing 6 Possible Candidates and 22 Redwala results; 6 remained unresolved because their daily responses contained fewer than four completed sessions.

Stocks lacking sufficient daily history remain unresolved. Recovery was simulated in tests; this intraday restart does not prove next-session 09:16 broker availability or guarantee a fixed completion time.

Request shapes and limits were checked against [Dhan historical-data documentation](https://dhanhq.co/docs/v2/historical-data/) and [rate limits](https://dhanhq.co/docs/v2/#rate-limit).
