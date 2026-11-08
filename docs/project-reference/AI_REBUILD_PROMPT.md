# AI rebuild prompt

Upload `PROJECT_SPECIFICATION.md` first. If multiple attachments are supported, include `MODEL_SCHEMAS.json`, `DEFAULT_SETTINGS.json`, `INTERFACES_AND_SOURCE_MAP.md` and `TEST_INVENTORY.md`. Extract the ZIP before uploading if the AI cannot read archives.

Copy the instruction below into your AI tool:

---

Build a working application from the attached Dhan Turnover Scanner specification. Treat this as a detailed product and implementation contract, not a request for a static dashboard mockup.

Use Python/FastAPI, Pydantic, SQLite and a plain HTML/CSS/JavaScript frontend unless I explicitly approve a different stack. Follow the exact settings defaults, units, strict versus inclusive boundaries, setup scope and persistence behavior in the attachments. Implement both frontend controls and the matching backend behavior. Read the whole specification before coding.

First produce a requirements-to-module/test map. Then implement incrementally, run meaningful automated checks with synthetic candles and a fake broker, and deliver a runnable project with launch instructions. Include the implemented default-ON verified circuit-band >=20% live display filter. Keep both UC/LC distance columns, hide unverified/lower/dynamic bands, preserve existing sorting, and never apply today's band data to historical backtests.

Essential invariants:

1. NSE equity only. No Afternoon scan or retired standalone Premarket Setup. Keep NSE pre-open CSV import and premarket historical caching.
2. Possible Candidate uses one green opening candle, daily ratio OR previous-day signed change <=+1%, first-minute relative volume, first turnover and its enabled filters. First-high breakout is an additional badge, not a mandatory base condition.
3. Redwala uses a red first candle, open=high and turnover, plus its own optional previous-close/tolerance rule. Do not apply Candidate relative-volume/daily/opening/resistance filters to Redwala.
4. Retest Break requires a red first candle then consecutive completed green candles through a strict first-high break, without missing minutes. It cannot start an algo.
5. Preserve the exact daily resistance selection and live-versus-replay rules. Do not introduce future daily bars or future intraday qualification into an earlier replay entry.
6. Keep badge combinations and group ordering exact. Preserve the documented backtest ordering difference. Display filters do not alter scanner qualification or running algos.
7. Use date-aware reusable historical caches, incremental SQLite writes, immediate memory publication, per-stock preparation and a fair shared historical scheduler. Missing data remains unresolved. Never promise all stocks will confirm by09:16.
8. Trading starts only after explicit stock selection. Default the browser to paper. No real order or account operation during development/testing.
9. UI algos use capital per entry/add, original ladder reference and initial-quantity reversal sizing. Track actual fills and weighted average cost separately from the target/stop reference.
10. Persist order intent before submission. An uncertain broker acknowledgement is reconciled by correlation ID, never blindly resent. Handle partial fills, deduplicate trades, compare broker/app quantity, block unexplained exposure and pause unfinished sessions on restart.
11. Use separate websocket LTP monitoring and order reconciliation. Fresh depth supports sizing/execution, but market orders do not guarantee the displayed price. Do not block tick processing on REST or disk operations.
12. Backtests use initial-candle close-only checks and candle-close-confirmed reversals; live/paper reversals use tick triggers. Do not invent a revisit to an opening high/low. Clearly disclose OHLC limitations.
13. Display cumulative gross P&L, estimated costs and net P&L correctly. Do not sum cumulative P&L rows or deduct slippage twice.
14. Keep credentials out of source, test fixtures, logs and artifacts. Bind locally. One execution server owns the journal. Do not enable real trading as part of testing.

Use the official Dhan documentation and the pinned SDK as integration references, verifying current contracts before enabling real orders. Fake-broker tests are necessary but do not certify live broker access or fills.

If a detail is unclear, record the ambiguity and make it reviewable. Do not silently change financial comparisons, algorithm timing, order retry rules or setup applicability. Deliver a feature checklist showing implemented, tested and still pending items, with commands to run the app and tests on Windows and macOS.

---

For rebuilding a later project version, replace this pack with documentation generated from that version. The manifest identifies the source files described here; a Git commit alone is insufficient when there are uncommitted changes.
