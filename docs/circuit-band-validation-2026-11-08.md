# Live circuit-band filter — implementation and validation

Completed 8 November 2026. Changes were tested in an isolated checkout and byte-verified when applied to the main project. No server was responding on port 8000 at deployment; no live feed or order session was interrupted. No broker orders were placed.

## Behavior

- **Only circuit band ≥20% · Live** is ON by default and saved in this browser. OFF restores otherwise matching rows immediately.
- Verify both upper and lower prices against a reference close. Prefer the same quote's `last_price - net_change`; otherwise use valid prior-session close data prepared for the current session.
- Recognize standard fixed 2/5/10/20% bands. Allow at most ₹0.05 rounding error per limit, capped at 0.1% of reference. Unrecognized or asymmetric limits remain unverified; unsupported larger-tick rounding is conservatively hidden.
- Eligibility requires a recognized band ≥20%. Known F&O symbols are classified as dynamic using the existing static list. This is validation against Dhan's returned prices, not independent exchange certification or a refreshed F&O-membership service.
- Hide lower, missing, invalid, inconsistent, previous-date, future-dated and over-120-second-old verification. Show hidden counts separately from total scanner matches.
- Keep UC Away % and LC Away % relative to LTP, and preserve existing badge priority and turnover sorting.
- Check for newly qualified stocks every two seconds. Each stock retains its 60-second quote-attempt interval and all quote requests retain the shared 1.05-second throttle. Dashboard toggles do not request data or change subscriptions.
- Do not change setup qualification, running algos or historical backtests. Today's limits cannot establish a historical circuit band.

## Integration references

[Dhan quote documentation](https://dhanhq.co/docs/v2/market-quote/) exposes current upper/lower circuit prices and absolute LTP change from previous close. [NSE price-band documentation](https://www.nseindia.com/static/products-services/equity-market-price-bands) distinguishes fixed bands from derivative-stock operating ranges. The filter never substitutes UC/LC distance for the nominal band.

## Validation

- Full isolated Python suite: **982 passed** in 97.35 seconds.
- Dashboard JavaScript suite: **46 passed**, executed through the Node VM test harness.
- New browser integration cases cover real FastAPI serialization and synthetic Dhan responses at desktop 1440px and mobile 390px widths, toggle persistence, retained distance columns, immediate stale-row removal and unaffected historical rendering.
- Backend cases cover standard bands, malformed/asymmetric/unrecognized data, positive and negative net changes, dated-cache fallback, known F&O, quote failure, rounding, timestamps, live LTP changes, and timely first quotes without refetching existing qualifiers.
- Existing browser fixtures explicitly disable the new gate when testing unrelated features without circuit data; the new tests exercise the actual default ON state.
- Existing application changes, user configuration, cached history and algo journals were preserved.

Tests use synthetic quotes and isolated storage. They do not certify a live broker account's data completeness. Restart the application and refresh the dashboard to load the updated backend and controls.
