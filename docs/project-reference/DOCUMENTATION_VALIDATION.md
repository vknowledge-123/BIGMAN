# Documentation validation

Date: 8 November 2026 (IST).

The following checks passed for this documentation pack:

- All 17 exported JSON model schemas match the current model definitions.
- Scanner, algo and CSV default exports round-trip through Pydantic and match source defaults.
- All 20 application routes are unique and documented in the main report.
- The static F&O export contains the same 210 symbols as the source.
- SHA-256 hashes match all 59 source files in the manifest after document generation.
- All JSON sidecars parse; the report's JSON request example validates as scanner settings.
- The report has 21 numbered main sections and balanced fenced code blocks.
- Numerical examples were checked for crore conversion, UC/LC distances, net P&L and combined reversal quantity.
- The ZIP contains only the explicitly selected documentation files and regeneration script, with no runtime data, credentials, cache databases, order journals or uploaded customer CSVs.

The test inventory records 296 Python test-function declarations and 46 named JavaScript tests. Parameterization can create additional cases. These numbers do not represent a fresh test run or pass count.

The original documentation-only checks did not execute the application suite. The subsequent circuit-band implementation was tested in an isolated checkout: **982 Python tests and 46 dashboard JavaScript checks passed**. All application and test source contents match the tested checkout, allowing for existing LF/CRLF line endings. The 16 deployed files were also byte-verified at copying. Browser integration used real FastAPI handlers and synthetic quotes at desktop and mobile widths.

The verified circuit-band >=20% live display filter is now implemented and documented in section 21. No server was responding on port 8000 when the change was deployed. No real broker order was submitted, and runtime data was preserved. See `../circuit-band-validation-2026-11-08.md` for validation scope.

To regenerate structural exports, run `py docs/project-reference/build_reference.py` from the source project root. The narrative report must be reviewed separately after behavior changes.
