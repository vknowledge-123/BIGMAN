from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, scanner


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
    assert "checked opening candle pairs" in response.json()["message"]
