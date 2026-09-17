from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .dhan_scanner import ScannerEngine, parse_symbols
from .schemas import ConfigOut, CredentialsIn, MessageOut, StateOut, SymbolsIn
from .storage import ConfigStore


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

store = ConfigStore()
scanner = ScannerEngine(store)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scanner.load_saved()
    yield
    scanner.stop()


app = FastAPI(title="Dhan Turnover Scanner", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config", response_model=ConfigOut)
def get_config() -> ConfigOut:
    config = store.load()
    return ConfigOut(
        has_credentials=bool(config.client_id and config.access_token),
        client_id=config.client_id,
        symbols_text="\n".join(config.symbols),
        cached_close_count=len(config.previous_closes),
    )


@app.post("/api/credentials", response_model=MessageOut)
def save_credentials(payload: CredentialsIn) -> MessageOut:
    store.update_credentials(payload.client_id, payload.access_token)
    return MessageOut(ok=True, message="Credentials saved")


@app.post("/api/symbols", response_model=MessageOut)
def save_symbols(payload: SymbolsIn) -> MessageOut:
    symbols = parse_symbols(payload.symbols_text)
    if not symbols:
        raise HTTPException(status_code=400, detail="Paste at least one stock symbol")
    store.update_symbols(symbols)
    try:
        unresolved = scanner.prepare_symbols(symbols)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if unresolved:
        return MessageOut(
            ok=True,
            message=f"Saved {len(symbols)} symbol(s). Unresolved: {', '.join(unresolved)}",
        )
    return MessageOut(ok=True, message=f"Saved {len(symbols)} symbol(s)")


@app.post("/api/cache", response_model=MessageOut)
def cache_data() -> MessageOut:
    try:
        cached = scanner.cache_previous_closes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return MessageOut(ok=True, message=f"Cached previous close for {len(cached)} stock(s)")


@app.post("/api/start", response_model=MessageOut)
def start_scan() -> MessageOut:
    try:
        scanner.start()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return MessageOut(ok=True, message="Live scan started")


@app.post("/api/stop", response_model=MessageOut)
def stop_scan() -> MessageOut:
    scanner.stop()
    return MessageOut(ok=True, message="Live scan stopped")


@app.post("/api/repair", response_model=MessageOut)
def repair_missing() -> MessageOut:
    try:
        repaired = scanner.repair_missing_candles()
        candidates = scanner.evaluate_opening_candidates()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return MessageOut(
        ok=True,
        message=f"Repaired {repaired} live candle(s); checked opening candle pairs, {candidates} possible candidate(s)",
    )


@app.get("/api/state", response_model=StateOut)
def get_state() -> dict:
    return scanner.snapshot()
