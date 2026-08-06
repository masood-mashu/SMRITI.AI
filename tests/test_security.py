from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.security import rate_limiter


def test_protected_routes_require_bearer_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SMRITI_API_TOKEN", "test-token")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "60")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/timeline").status_code == 401
        response = client.get("/timeline", headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"]


def test_rate_limit_is_enforced_per_client(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    rate_limiter._events.clear()
    with TestClient(app) as client:
        assert client.get("/timeline").status_code == 200
        assert client.get("/timeline").status_code == 429
