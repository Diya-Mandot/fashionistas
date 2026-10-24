from fastapi.testclient import TestClient

from app.main import app
from app.config import Settings, get_settings


def test_health():
    res = TestClient(app).get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_api_configuration_does_not_claim_verification():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, openai_api_key="do-not-expose")
    try:
        res = TestClient(app).get("/api/health/apis")
        assert res.status_code == 200
        assert res.json()["verified"] is False
        assert res.json()["key_configured"] is True
        assert res.json()["agents"]["runtime"] == "agents_sdk"
        assert "do-not-expose" not in res.text
    finally:
        app.dependency_overrides.clear()


def test_preflight_labels_mock_without_claiming_live_access():
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, agents_mode="mock", decisions_mode="mock", openai_api_key="")
    try:
        res = TestClient(app).post("/api/health/apis/check")
        assert res.status_code == 200
        for provider in ("agents", "decisions"):
            assert res.json()[provider]["source"] == "mock"
            assert res.json()[provider]["live_verified"] is False
    finally:
        app.dependency_overrides.clear()


def test_preflight_reports_missing_keys():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, openai_api_key="")
    try:
        res = TestClient(app).post("/api/health/apis/check")
        assert res.status_code == 200
        assert res.json()["agents"]["ok"] is False
        assert res.json()["decisions"]["ok"] is False
        assert "OPENAI_API_KEY" in res.json()["agents"]["error"]
    finally:
        app.dependency_overrides.clear()
