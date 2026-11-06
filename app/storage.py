from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

from .schemas import VolumeFilterSettings
from .history_cache import HistoryCache


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_PATH = DATA_DIR / "config.json"


@dataclass
class AppConfig:
    volume_filters: VolumeFilterSettings = field(default_factory=VolumeFilterSettings)
    client_id: str = ""
    access_token: str = ""
    symbols: list[str] = field(default_factory=list)
    previous_closes: dict[str, float] = field(default_factory=dict)
    opening_volume_cache: dict[str, dict[str, Any]] = field(default_factory=dict)


class ConfigStore:
    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.history = HistoryCache(self.path.with_name(self.path.stem + '-cache.sqlite3'))

    def load(self, *, include_cache: bool = True) -> AppConfig:
        with self._lock:
            raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
            if 'opening_volume_cache' in raw or 'previous_closes' in raw:
                # Commit data first. If JSON replacement fails, the next load safely retries.
                self.history.update(raw.get('opening_volume_cache'), raw.get('previous_closes'), legacy=True)
                raw.pop('opening_volume_cache', None)
                raw.pop('previous_closes', None)
                self._save_settings(raw)
            entries, closes = self.history.load() if include_cache else ({}, {})
            return AppConfig(
                volume_filters=VolumeFilterSettings.model_validate(raw.get("volume_filters") or {}),
                client_id=str(raw.get("client_id", "")),
                access_token=str(raw.get("access_token", "")),
                symbols=[str(item).upper() for item in raw.get("symbols", [])],
                previous_closes={
                    str(symbol).upper(): float(close)
                    for symbol, close in closes.items()
                    if close is not None
                },
                opening_volume_cache={
                    str(symbol).upper(): value
                    for symbol, value in entries.items()
                    if isinstance(value, dict)
                },
            )

    def save(self, config: AppConfig) -> None:
        with self._lock:
            payload: dict[str, Any] = {
                "volume_filters": config.volume_filters.model_dump(),
                "client_id": config.client_id,
                "access_token": config.access_token,
                "symbols": config.symbols,
            }
            if config.previous_closes or config.opening_volume_cache:
                self.history.update(config.opening_volume_cache, config.previous_closes)
            self._save_settings(payload)

    def _save_settings(self, payload: dict) -> None:
        tmp_path = self.path.with_suffix('.tmp')
        tmp_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        tmp_path.replace(self.path)

    def update_credentials(self, client_id: str, access_token: str) -> AppConfig:
        with self._lock:
            config = self.load(include_cache=False)
            client_id, access_token = client_id.strip(), access_token.strip()
            if not client_id:
                raise ValueError("Enter a Client ID")
            if not access_token:
                if client_id != config.client_id or not config.access_token:
                    raise ValueError("Enter an access token for this Client ID")
                return config  # Blank means keep this account's saved token.
            config.client_id = client_id
            config.access_token = access_token
            self.save(config)
            return config

    def update_volume_filters(self, settings: VolumeFilterSettings) -> AppConfig:
        with self._lock:
            config = self.load(include_cache=False)
            config.volume_filters = settings
            self.save(config)
            return config

    def update_symbols(self, symbols: list[str]) -> AppConfig:
        with self._lock:
            config = self.load(include_cache=False)
            config.symbols = symbols
            self.save(config)
            return config

    def load_preopen_import(self) -> dict | None:
        with self._lock:
            path = self.path.with_name(self.path.stem + "-preopen.json")
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def save_preopen_import(self, payload: dict) -> None:
        with self._lock:
            path = self.path.with_name(self.path.stem + "-preopen.json")
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            temporary.replace(path)

    def update_previous_closes(self, previous_closes: dict[str, float]) -> None:
        with self._lock:
            self.load(include_cache=False)  # Upgrade a legacy file once, before writing new values.
            self.history.update(closes=previous_closes)

    def update_opening_volume_cache(self, entries: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            self.load(include_cache=False)
            self.history.update(entries=entries)
