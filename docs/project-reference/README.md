# Project documentation pack

Start with **PROJECT_SPECIFICATION.md**. It explains the full product, formulas, feature scopes, user interface, cache pipeline, backtests, order handling and operational limits.

| File | Purpose |
|---|---|
| `SECURITY.md` | Threat protections, exact limits, dependencies, deployment and maintenance |
| `MEMBER_HOSTING.md` | Account roles, TOTP, admin approval, shared settings, hosting and recovery |
| `PROJECT_SPECIFICATION.md` | Main detailed report; best single file to upload to an AI |
| `AI_REBUILD_PROMPT.md` | Copy-and-paste instructions for rebuilding the application |
| `INTERFACES_AND_SOURCE_MAP.md` | Routes, model fields, module/function map and frontend controls |
| `MODEL_SCHEMAS.json` | Exact JSON schemas for request/response and settings models |
| `DEFAULT_SETTINGS.json` | Source defaults, browser policies and local display defaults |
| `API_ROUTES.json` | Machine-readable inventory of application routes |
| `FNO_SYMBOLS.json` | Static classification list required to reproduce CSV selection |
| `TEST_INVENTORY.md` | Test declarations organized by source file; not a pass report |
| `SOURCE_MANIFEST.json` | Source hashes identifying the documented code snapshot |
| `build_reference.py` | Regenerates structural sidecars from the source project |
| `DOCUMENTATION_VALIDATION.md` | Checks performed on the documentation pack |

The report describes the main source on **11 November 2026**, including the completed verified circuit-band >=20% live display filter. Section21 explains its implementation, default-ON toggle and historical-backtest exclusion.

For another AI tool, upload the main report and the rebuild prompt. Add the JSON schemas, defaults, F&O list and test inventory when attachments allow. ZIP files should be extracted first if the receiving tool cannot inspect archives.

This pack includes no account credentials or runtime trading records. Sharing the actual project is a separate operation; do not include private `data/` files just because these documentation files are shareable.

To regenerate structural sidecars from the project root:

```powershell
py docs/project-reference/build_reference.py
```

The generator reads source and imports only pure model/helper modules. It does not import `app.main`, connect to Dhan, start a server or read account storage. The narrative report and rebuild prompt require human/AI review when behavior changes; they are not regenerated automatically.
