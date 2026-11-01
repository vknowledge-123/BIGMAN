# Integration audit — 31 October 2026

## Results

- Full Python suite after fixes: **887 passed** (`py -m pytest -q`, 81.11 seconds).
- JavaScript dashboard regression checks: **38 passed**.
- All application and launcher Python files parsed successfully; compilation passed for `app`, `scripts` and `tests`.
- HTML check: **126 unique IDs**, no duplicate IDs or missing statically referenced dashboard/import controls.
- `git diff --check`: passed.
- Headless Edge desktop/mobile integration workflows passed; generated screenshots are in `docs/algo-test-artifacts/`. The mobile scanner screenshot was also visually inspected.

## Fixes made in this audit

1. **Manual stock-list save on resolution failure.** Previously `/api/symbols` persisted the new list before looking up instruments. If lookup failed, saved configuration and the running scanner disagreed. Instrument preparation now happens before the list is saved. A regression test verifies both the old saved list and running states survive lookup failure.
2. **Backtest settings changed by another tab.** Saving filters and starting a backtest are separate HTTP requests. Another client could save different filters between them. The dashboard now includes its selected scanner settings in the backtest request. The backend uses that immutable request snapshot, without overwriting current Live settings. Older API clients that omit the snapshot still use saved settings. Tests cover request validation, another tab's settings, legacy behavior and cleanup after a failed run.
3. **IST dates and unambiguous candle labels.** Date-picker defaults and bounds previously followed the browser's local calendar. They now use Asia/Kolkata and calendar offsets independent of the browser timezone. Candle times use 24-hour IST so afternoon labels do not lose their AM/PM distinction when shortened. Tests include UTC/month boundaries.
4. **Launcher response validation.** A different service on the scanner port could return valid JSON with an unexpected shape and crash the readiness probe. The launcher now checks the schema and info object types before identifying the scanner. Tests cover unrelated applications, malformed response shapes and timeouts; the launcher never kills the existing process.

## Integration coverage

- FastAPI request/response schemas, settings persistence, blank-token credential reuse and stale UI responses.
- Manual symbol entry and NSE CSV import, including F&O/non-F&O selection, invalid files and saved import restoration.
- Daily/first-minute volume, turnover, opening-gap and tolerance rules, PDHL, five-session open cross, monthly and last-two-session filters.
- Setup-specific exemptions for Redwala and Retest Break; missing-history handling and cache reuse.
- Live previews, completed-candle confirmation, first-candle break badges and previous-day crosses.
- Live/backtest display volume and price filters, strict thresholds, persisted preferences, turnover ordering and visible-result summaries.
- Scanner backtests, original opening-gap inputs, first-candle close in API results and stale-result warnings.
- Paper trading and historical ladder/pyramid simulations; costs and P&L display; startup, exits, partial fills, uncertain order submissions, reconciliation and duplicate/mismatched trade handling.
- Installed Dhan SDK adapter contract tests with fake HTTP transport, websocket packet parsing, freshness checks and reconnect/fallback behavior.
- Removed Afternoon/Premarket setup endpoints remain unavailable.

## Boundaries

Tests used isolated configuration/journals and fake broker transports. No real orders were submitted, and the running trading server was not deliberately stopped or restarted. This audit establishes that the covered scenarios pass; it is not a claim that every possible broker, network or market condition is bug-free. Actual live fills and macOS execution were not exercised in this Windows test run.

Existing user changes, including the trading journal and the previous opening-gap audit, were retained. Restart the application after active algos have been safely stopped, then refresh the dashboard to load the backend and frontend changes together.
