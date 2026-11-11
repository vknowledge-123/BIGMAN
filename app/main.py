from __future__ import annotations

from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI, HTTPException, APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from .security import SecurityMiddleware

from .dhan_scanner import ScannerEngine, parse_symbols
from .schemas import (
    BacktestIn,
    BacktestOut,
    ConfigOut,
    CredentialsIn,
    MessageOut,
    StateOut,
    SymbolsIn,
    VolumeFilterSettings,
)
from .storage import ConfigStore
from . import access
from .accounts import AccountError
from .member_view import PublishedDashboard
from .algo_strategy import AlgoSettings, AlgoStart, AlgoBacktest
from .preopen import PreopenRequest, PreopenSettings, filter_csv


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

store = ConfigStore()
scanner = ScannerEngine(store)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scanner.load_saved()
    yield
    if scanner._algo is not None:
        scanner._algo.shutdown()
    scanner.stop()


app = FastAPI(title="Dhan Turnover Scanner", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
admin_api = APIRouter(dependencies=[Depends(access.require_admin)])
published = PublishedDashboard()
app.include_router(access.router)


@app.exception_handler(AccountError)
async def account_error(request, exc):
    return JSONResponse({"detail":str(exc)},status_code=exc.status,
                        headers={"Retry-After":"900"} if exc.status==429 else None)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic includes submitted input and context by default, including passwords.
    return JSONResponse({"detail":[{k:e[k] for k in ("loc","msg","type") if k in e}
                                   for e in exc.errors()]}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    # Do not echo exception text, account material or broker payloads to a browser.
    import logging
    logging.getLogger("scanner.security").error("Unhandled request error: %s", type(exc).__name__)
    return JSONResponse({"detail":"An internal error occurred. Contact the administrator."},status_code=500,
                        headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


@app.get('/health')
def health():
    return {"info":{"title":"Dhan Turnover Scanner"}}


@app.get('/openapi.json', dependencies=[Depends(access.require_admin)])
def protected_schema():
    return app.openapi()


@app.middleware("http")
async def prevent_cached_api_state(request, call_next):
    if request.url.path.startswith("/static/") and request.url.path.lower().endswith(".html"):
        return JSONResponse({"detail":"Not found"},status_code=404)
    response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path in ("/", "/login", "/signup"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path not in ("/docs", "/redoc", "/docs/oauth2-redirect"):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response

app.add_middleware(SecurityMiddleware)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def dashboard(user=Depends(access.optional_user)):
    if not user:
        return RedirectResponse("/login",status_code=303)
    if user["role"] != "admin":
        return HTMLResponse((STATIC_DIR / "member.html").read_text(encoding="utf-8"))
    # HTML and controls must stay in sync after updates, including Drive copies.
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for filename in ("app.js", "styles.css", "preopen.js", "account.js", "shared-admin.js"):
        if f'"/static/{filename}"' not in html:
            continue
        version = sha256((STATIC_DIR / filename).read_bytes()).hexdigest()[:16]
        html = html.replace(f'"/static/{filename}"', f'"/static/{filename}?v={version}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@admin_api.get("/api/config", response_model=ConfigOut)
def get_config() -> ConfigOut:
    config = store.load()
    return ConfigOut(
        volume_filters=config.volume_filters,
        display_filters=access.accounts.display(),
        has_credentials=bool(config.client_id and config.access_token),
        client_id=config.client_id,
        symbols_text="\n".join(config.symbols),
        cached_close_count=len(config.previous_closes),
        cached_volume_count=len(config.opening_volume_cache),
    )


@admin_api.post("/api/volume-filters", response_model=MessageOut)
def save_volume_filters(payload: VolumeFilterSettings) -> MessageOut:
    return MessageOut(ok=True, message=scanner.update_volume_filters(payload))


@admin_api.post("/api/credentials", response_model=MessageOut)
def save_credentials(payload: CredentialsIn) -> MessageOut:
    try:
        store.update_credentials(payload.client_id, payload.access_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageOut(ok=True, message="Credentials saved; reused automatically after browser refresh")


@admin_api.post("/api/symbols", response_model=MessageOut)
def save_symbols(payload: SymbolsIn) -> MessageOut:
    symbols = parse_symbols(payload.symbols_text)
    if not symbols:
        raise HTTPException(status_code=400, detail="Paste at least one stock symbol")
    try:
        unresolved = scanner.prepare_symbols(symbols)
        store.update_symbols(symbols)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if unresolved:
        return MessageOut(
            ok=True,
            message=f"Saved {len(symbols)} symbol(s). Unresolved: {', '.join(unresolved)}",
        )
    return MessageOut(ok=True, message=f"Saved {len(symbols)} symbol(s)")


@admin_api.get("/api/preopen")
def get_preopen_import():
    return {"saved": store.load_preopen_import(), "defaults": PreopenSettings().model_dump()}


@admin_api.post("/api/preopen/preview")
def preview_preopen(payload: PreopenRequest):
    try:
        return filter_csv(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_api.post("/api/preopen/apply")
def apply_preopen(payload: PreopenRequest):
    result = preview_preopen(payload)
    if not result["symbols"]:
        raise HTTPException(status_code=400, detail="No matching stocks. The scanner list has not been changed.")
    try:
        unresolved = scanner.prepare_symbols(result["symbols"])
        store.update_symbols(result["symbols"])
        store.save_preopen_import(payload.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    label = "F&O" if payload.settings.universe == "fno" else "Cash (non-F&O)"
    return {**result, "unresolved_symbols": unresolved,
            "message": f"Loaded {len(result['symbols'])} {label} stocks into the scanner. Cache Volume + Day Levels, then Start Live."
                       + (f" {len(unresolved)} symbol(s) could not be resolved." if unresolved else "")}


@admin_api.post("/api/cache", response_model=MessageOut)
def cache_data() -> MessageOut:
    try:
        cached = scanner.cache_previous_closes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return MessageOut(ok=True, message=f"Cached previous close for {len(cached)} stock(s)")


@admin_api.post("/api/cache-volume", response_model=MessageOut)
def cache_volume_average() -> MessageOut:
    try:
        cached = scanner.cache_opening_volume_averages()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return MessageOut(
        ok=True,
        message=f"Cached opening volume average, previous-day check and high/low for {len(cached)} stock(s)",
    )


@admin_api.post("/api/backtest", response_model=BacktestOut)
def run_backtest(payload: BacktestIn) -> dict:
    try:
        if payload.volume_filters is not None:
            return scanner.backtest_date(payload.target_date, volume_filters=payload.volume_filters)
        return scanner.backtest_date(payload.target_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc




@admin_api.post("/api/start", response_model=MessageOut)
def start_scan() -> MessageOut:
    try:
        scanner.start()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return MessageOut(ok=True, message="Live scan started")


@admin_api.post("/api/stop", response_model=MessageOut)
def stop_scan() -> MessageOut:
    scanner.stop()
    return MessageOut(ok=True, message="Live scan stopped")


@admin_api.post("/api/repair", response_model=MessageOut)
def repair_missing() -> MessageOut:
    try:
        repaired = scanner.repair_missing_candles()
        candidates = scanner.evaluate_opening_candidates()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return MessageOut(
        ok=True,
        message=(
            f"Repaired {repaired} live candle(s); checked first candle and both volume rules, "
            f"{candidates} possible candidate(s)"
        ),
    )


@admin_api.get("/api/state", response_model=StateOut)
def get_state() -> dict:
    return {**scanner.snapshot(), "algo": scanner.algo.snapshot(), "display_filters": access.accounts.display()}


@admin_api.post('/api/algo/settings', response_model=MessageOut)
def save_algo_settings(payload: AlgoSettings):
    scanner.algo.save_settings(payload)
    return MessageOut(ok=True, message='Algo defaults saved; active sessions keep their original settings')


@admin_api.post('/api/algo/start')
def start_algo(payload: AlgoStart):
    try:
        session_id = scanner.algo.start(payload)
        return {'ok': True, 'session_id': session_id, 'message': f'{payload.settings.mode.title()} algo queued for {payload.symbol}'}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_api.post('/api/algo/{session_id}/exit', response_model=MessageOut)
def exit_algo(session_id: str):
    try:
        scanner.algo.command(session_id, 'exit')
        return MessageOut(ok=True, message='Exit requested; waiting for reconciled flat position')
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_api.post('/api/algo/{session_id}/resume', response_model=MessageOut)
def resume_algo(session_id: str):
    try:
        scanner.algo.command(session_id, 'resume')
        return MessageOut(ok=True, message='Reconciliation requested before resuming')
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_api.post('/api/algo/backtest')
def backtest_algo(payload: AlgoBacktest):
    try:
        return scanner.algo.backtest(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


app.include_router(admin_api)


@app.get('/login', response_class=HTMLResponse)
@app.get('/signup', response_class=HTMLResponse)
def auth_page(request: Request):
    access.transport(request)
    return HTMLResponse((STATIC_DIR/'auth.html').read_text(encoding='utf-8'))


@app.get('/api/member/state')
def member_state(_=Depends(access.require_member)):
    return published.snapshot(scanner, access.accounts.display())
