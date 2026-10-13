from __future__ import annotations

import re

from fastapi.testclient import TestClient
import pytest

from app.main import app, scanner
from app.storage import ConfigStore
from app.schemas import VolumeFilterSettings


@pytest.fixture(autouse=True)
def isolated_app(monkeypatch, tmp_path):
    # API tests must never load the user's saved credentials or contact Dhan.
    store = ConfigStore(tmp_path / "config.json")
    monkeypatch.setattr("app.main.store", store)
    monkeypatch.setattr(scanner, "store", store)
    monkeypatch.setattr(scanner, "_states", {})
    monkeypatch.setattr(scanner, "_volume_filters", VolumeFilterSettings())
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


def test_dashboard_versions_assets_and_does_not_cache_html(monkeypatch, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text('<script src="/static/app.js"></script><link href="/static/styles.css">')
    (static / "app.js").write_text("old controls")
    (static / "styles.css").write_text("body {}")
    monkeypatch.setattr("app.main.STATIC_DIR", static)
    with TestClient(app) as client:
        before = client.get("/")
        assert before.headers["cache-control"] == "no-store"
        script_before = re.search(r'/static/app.js\?v=[a-f0-9]+', before.text).group()
        css_before = re.search(r'/static/styles.css\?v=[a-f0-9]+', before.text).group()
        (static / "app.js").write_text("new monthly filter controls")
        after = client.get("/")
        assert script_before not in after.text
        assert css_before in after.text


def test_dashboard_serves_current_versioned_filter_script():
    with TestClient(app) as client:
        page = client.get("/")
        script_url = re.search(r'src="(/static/app.js\?v=[a-f0-9]+)"', page.text).group(1)
        script = client.get(script_url)
    assert script.status_code == 200
    assert "settings.monthly_filter = Boolean(els.monthlyFilter.checked)" in script.text
    assert "Monthly Filter" in script.text


def test_volume_settings_endpoint_persists_and_returns_current_settings():
    settings = {"daily_volume_max": 2.5, "minute_volume_min": 6, "first_candle_turnover_min": 12_500_000, "today_open_cross": True,
                "monthly_filter": True, "last_two_days_filter": True}
    with TestClient(app) as client:
        assert client.post("/api/volume-filters", json=settings).status_code == 200
        assert client.get("/api/config").json()["volume_filters"] == settings
        assert client.get("/api/state").json()["volume_filters"] == settings
        for field in ("minute_volume_min", "first_candle_turnover_min"):
            for value in (0, -2, "NaN", "Infinity"):
                response = client.post("/api/volume-filters", json={**settings, field: value})
                assert response.status_code == 422
        assert client.get("/api/config").json()["volume_filters"] == settings


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
    assert "checked first candle and both volume rules" in response.json()["message"]


def test_cache_volume_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(scanner, "cache_opening_volume_averages", lambda: {"AAA": 1250.0})

    with TestClient(app) as client:
        response = client.post("/api/cache-volume")

    assert response.status_code == 200
    assert response.json()["message"] == "Cached opening volume average, previous-day check and high/low for 1 stock(s)"


def test_backtest_endpoint(monkeypatch) -> None:
    result = {
        "warning_count": 0,
        "scan_type": "opening",
        "volume_filters": VolumeFilterSettings().model_dump(),
        "target_date": "2026-08-26",
        "stocks": [],
        "tested_count": 0,
        "four_x_count": 0,
        "candidate_count": 0,
        "qualified_count": 0,
        "redwala_count": 0,
        "retest_count": 0,
        "error_count": 0,
    }
    monkeypatch.setattr(scanner, "backtest_date", lambda _target_date: result)

    with TestClient(app) as client:
        response = client.post("/api/backtest", json={"target_date": "2026-08-26"})

    assert response.status_code == 200
    assert response.json() == result


def test_removed_premarket_setup_cannot_start_or_backtest(monkeypatch):
    calls = []
    monkeypatch.setattr(scanner, 'backtest_date', lambda *args, **kwargs: calls.append(args))
    with TestClient(app) as client:
        assert client.post('/api/premarket/start').status_code == 404
        for mode in ('premarket', 'bad'):
            assert client.post('/api/backtest', json={'target_date': '2026-10-01', 'scan_type': mode}).status_code == 422
        state = client.get('/api/state').json()
        assert not any(key.startswith('premarket_') for key in state)
    assert calls == []
    assert not hasattr(scanner, 'start_premarket')




