# Integration audit - 17 October 2026

Reviewed the scanner, cache/filter logic, FastAPI routes and schemas, browser dashboard, ladder/replay strategy, execution service, journal, Dhan SDK adapter and both websocket integrations.

## Fixes

1. **REST quote fallback:** unpack the quote endpoint's own status/data envelope inside SDK 2.2.0's envelope. Propagate inner failures. Keep valid LTP available when bid/ask is absent, so a live flatten can still trigger. Measure freshness after the request completes while preserving request-start ordering against newer websocket ticks.
2. **Cancellation responses:** accept documented empty HTTP 202/204 success bodies in the trading adapter. Order/trade/position reconciliation still determines the actual cancellation and remaining exposure.
3. **Fill identity:** verify the returned order ID, correlation ID for uncertain submissions, supplied account IDs, and non-null trade IDs before applying fills. A mismatched response cannot become a fill in the selected session.
4. **Square-off race:** recheck square-off after broker preflight and before sending. Do not open a position after cutoff; flatten existing exposure. Block submission if credentials change during preflight.
5. **Backtest presentation:** label the fill table as cumulative gross P&L; show gross minus costs equals net. Mark a result stale after its inputs or saved scanner filters change, including edits made while a backtest runs.
6. **Validation messages:** show API validation field names and reasons instead of `[object Object]`.

## Verification scope

- Existing regression tests cover daily/minute volume thresholds, turnover boundaries, opening filters, PDH/PDL badges, first-candle breaks, Retest Break, caching, live preparation, scanner backtests, settings updates and removed Afternoon/Premarket setup endpoints.
- A new browser integration test routes actual dashboard actions into isolated FastAPI, storage, filter, cache and backtest code. It checks decimal filter saves, opening-filter toggles, Redwala exemptions, setup selection, responsive layout and browser errors.
- Eight browser algo scenarios cover Possible Candidate and Redwala, setup-default and long-first direction, morning and afternoon times, paper entry/exit, cancelled live confirmation, backtest replay, stale-result warnings and cost display. Mobile page overflow is checked.
- Real installed Dhan SDK methods are exercised with the HTTP transport replaced: nested quote responses, endpoint paths, market/intraday order payloads, correlation IDs and empty cancellation responses.
- Execution regressions include partial fills, uncertain submissions, duplicate trades, identity mismatches, quantity reconciliation, rejection handling, trailing/reversal behavior, transient websocket touches, reconnect/subscription behavior, stale packets and quote fallback.
- Read-only local-app smoke check confirmed updated dashboard markup and no active algo sessions.

## Results

- `py -m pytest -q`: **666 passed**, including nine headless Edge frontend/backend scenarios.
- Dashboard JavaScript regression checks: **26 passed**.
- Python compilation and `git diff --check`: passed.
- No tests sent real orders.

## Dhan documentation reviewed

- [Orders and cancellation](https://dhanhq.co/docs/v2/orders/)
- [Order updates](https://dhanhq.co/docs/v2/order-update/)
- [Positions](https://dhanhq.co/docs/v2/portfolio/)
- [Market quotes](https://dhanhq.co/docs/v2/market-quote/)
- [Market websocket](https://dhanhq.co/docs/v2/live-market-feed/)
- [Historical data](https://dhanhq.co/docs/v2/historical-data/)
- [Rate limits](https://dhanhq.co/docs/v2/)

Historical requests retain 0.23-second spacing and quote requests share 1.05-second spacing. Existing history requests use windows below the documented 90-day per-request maximum. Market-feed subscriptions use batches of at most 100 instruments; Full packets use the documented 162-byte format. Broker order and portfolio calls retain their aggregate spacing. Broker minute/hour/day limits and account activity outside this app still apply.

## Limits of this audit

No real orders were submitted or cancelled. Broker authentication, static-IP whitelisting, market-hours connectivity, margin, actual fills, exchange rejection behavior and real-world latency were not certified against a funded account. Tests use synthetic market data and simulated broker responses; they cannot establish that every production failure is covered. App-managed exits still require a running server and fresh data. Backtests retain their explicitly different OHLC/candle-close assumptions.

Screenshots are in `docs/algo-test-artifacts/`, including scanner desktop/mobile and algo desktop/mobile views.
