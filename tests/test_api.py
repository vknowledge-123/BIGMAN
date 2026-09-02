from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


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
