from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import app, scanner
from app.storage import ConfigStore


@pytest.fixture(autouse=True)
def isolated_app(monkeypatch, tmp_path):
    # API tests must never load the user's saved credentials or contact Dhan.
    store = ConfigStore(tmp_path / "config.json")
    monkeypatch.setattr("app.main.store", store)
    monkeypatch.setattr(scanner, "store", store)
    monkeypatch.setattr(scanner, "_states", {})
    monkeypatch.setattr(scanner, "load_saved", lambda: None)


def test_config_and_state_endpoints_respond() -> None:
    with TestClient(app) as client:
        config_response = client.get("/api/config")
        state_response = client.get("/api/state")
        dashboard_response = client.get("/")

    assert config_response.status_code == 200
    assert state_response.status_code == 200
    assert dashboard_response.status_code == 200
    assert "Turnover Scanner" in dashboard_response.text
    assert "stocks" in state_response.json()


def test_symbols_endpoint_rejects_empty_list() -> None:
    with TestClient(app) as client:
        response = client.post("/api/symbols", json={"symbols_text": "   "})

    assert response.status_code == 400


def test_repair_endpoint_checks_opening_candidates(monkeypatch) -> None:
    calls = {"repair": 0, "candidates": 0}

    def fake_repair() -> int:
        calls["repair"] += 1
        return 2

    def fake_candidates() -> int:
        calls["candidates"] += 1
        return 1

    monkeypatch.setattr(scanner, "repair_missing_candles", fake_repair)
    monkeypatch.setattr(scanner, "evaluate_opening_candidates", fake_candidates)

    with TestClient(app) as client:
        response = client.post("/api/repair")

    assert response.status_code == 200
    assert calls == {"repair": 1, "candidates": 1}
    assert "checked opening colors and both volume rules" in response.json()["message"]


def test_cache_volume_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(scanner, "cache_opening_volume_averages", lambda: {"AAA": 1250.0})

    with TestClient(app) as client:
        response = client.post("/api/cache-volume")

    assert response.status_code == 200
    assert response.json()["message"] == "Cached opening volume average and previous-day check for 1 stock(s)"


def test_backtest_endpoint(monkeypatch) -> None:
    result = {
        "target_date": "2026-08-26",
        "stocks": [],
        "tested_count": 0,
        "four_x_count": 0,
        "candidate_count": 0,
        "qualified_count": 0,
        "redwala_count": 0,
        "error_count": 0,
    }
    monkeypatch.setattr(scanner, "backtest_date", lambda _target_date: result)

    with TestClient(app) as client:
        response = client.post("/api/backtest", json={"target_date": "2026-08-26"})

    assert response.status_code == 200
    assert response.json() == result
