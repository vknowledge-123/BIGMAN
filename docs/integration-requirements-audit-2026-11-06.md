# Integration and requirements audit — 6 November 2026

## Result

**956 Python tests passed in 95.36 seconds. All 43 JavaScript dashboard checks passed.** Python compilation and diff whitespace checks passed. Browser tests exercised the actual FastAPI handlers and response models in headless Edge at desktop and mobile widths. External broker transport used test doubles; no real orders were placed.

Tests ran in an isolated checkout containing the latest under_3.5% badge change. Production credentials, saved settings, stock lists, historical caches and algo journal were not copied into the tests. The installed Python 3.11.2 environment matches the pinned application dependency versions in requirements.txt.

## Reproduced bugs and fixes

1. **Stop/reload could hang indefinitely during SDK feed shutdown.** Dhan SDK 2.2.0's synchronous close wrapper waits on a future without a deadline. The scanner now uses a bounded asynchronous disconnect on the feed's loop, cancels/aborts a stuck connection, and bounds the fallback close for feeds whose loop never started. Scanner state is detached before cleanup, so late callbacks cannot disconnect a replacement feed. This affects the scanner feed, not the independent algo feeds.
2. **Today Open Cross could remain unresolved after an incomplete cache.** If the raw daily cache contained only four sessions, enabling the five-close condition could repeatedly reuse that cache rather than ask for the missing history. Cache validation now includes the enabled five-close requirement. A regression test first populates the incomplete cache, enables the toggle, provides corrected broker history and verifies that the stock qualifies after a real refresh.

Both defects were reproduced by failing tests before the fixes. A thread test double was extended to support the bounded shutdown's join/is_alive calls. Documentation also removes an outdated sorting description and documents the new opening-gap badge.

## Requirements checked

| Requirement | Evidence / scope |
|---|---|
| Possible Candidate uses the first green candle, daily rule, minute multiplier and strict turnover threshold | First-candle, daily-filter, turnover, staged-scan and integration suites; equality/failure/missing-data cases |
| No mandatory First Candle High Break for Possible Candidate | Browser-to-API live/backtest test qualifies green candles without later candles or a high-break badge |
| Redwala: red first candle, open = high, turnover; no volume multipliers | Redwala/price-filter suites, including daily-volume failures and incomplete optional history |
| Redwala open-or-close distance and optional opening tolerance | Price-filter boundary and live/backtest tests |
| Today Open Cross, monthly, last-two-days, Possible-only opening gap and PDHL | Toggle persistence, boundaries, setup scope, cache refresh and API replay tests |
| Daily resistance selection and delayed qualification | Resistance suite covers dated swing selection, confirmation/age/pullback/buffer, later live crossings and replay without future data |
| under_3.5% badge | Live and backtest tables consume actual backend first open and previous close. +3.5% and -3.5% included; above-limit, missing/invalid prices, Redwala, Retest-only and provisional rows excluded. Independent of toggle/limit |
| Breakout badges and PDL crosses | First-high/low break, strict first/second PDL open-close crossing and equality tests |
| Dashboard priority and turnover sorting | Complete Possible combination first, then three/four-badge Redwala, then other rows; descending first-candle turnover within groups |
| Volume display and maximum-price filters | Live/backtest boundaries, current LTP versus historical first close, persistence and mobile/browser tests |
| Premarket preparation/cache performance design | SQLite migration, concurrent/stale writes, 266-stock batching, dated rollover, fair request scheduling, missing-opening recovery and continued unresolved retries |
| Settings and credentials | Browser refresh/blank-token save, unapplied draft protection, no network/bulk-cache write during Save & Apply, per-request backtest settings |
| NSE CSV import | Rupee/crore units, inclusive thresholds, Cash/F&O selection, duplicates, Top N, preview/apply/reload and failed imports |
| Algo trading and replay | Direction selection, capital sizing, original-entry levels, SL/TSL/target, pyramiding/reversal limits, partial/duplicate fills, quantity mismatch, uncertain order submission, square-off, fees/slippage and OHLC timing regressions |
| Scanner/Algo independence and removed features | Scanner Stop, failed startup, late history responses; afternoon/premarket setup endpoints remain removed; scanner and algo endpoints remain available |
| Launch and API integration | Windows launcher tests, configuration/state/repair/cache/backtest endpoints, response schema and versioned static assets |

Representative test files: test_audit_regressions.py, test_dashboard_integration.py, test_dashboard.cjs, test_integration_workflows.py, test_cache_pipeline.py, test_dhan_contracts.py, test_algo.py, test_algo_feed.py and test_algo_browser.py. The full tests directory was executed.

## Broker checks and limits of this audit

Installed-SDK transport tests exercise order bodies, quote envelopes, empty cancellation responses and order/trade/account identity checks. Request shapes were cross-checked against Dhan's [historical data](https://dhanhq.co/docs/v2/historical-data/), [orders](https://dhanhq.co/docs/v2/orders/) and [market feed](https://dhanhq.co/docs/v2/live-market-feed/) documentation.

Passing tests establishes the covered behavior, not that every possible bug has been eliminated. This audit did not submit live demat orders or measure a new 09:16 opening run. Actual broker fills, feed availability and network latency remain outside the simulated tests.
