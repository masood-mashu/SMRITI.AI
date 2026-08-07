from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.security import AuthContext, rate_limiter


def test_protected_routes_require_bearer_when_enabled(monkeypatch) -> None:
    rate_limiter._events.clear()
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


def test_oidc_context_is_restricted_to_claimed_patient(monkeypatch) -> None:
    rate_limiter._events.clear()
    patient_id = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("OIDC_AUDIENCE", "smriti-api")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setattr(
        "backend.app.security._oidc_context",
        lambda token, settings: AuthContext(subject="user-1", patient_id=patient_id, mode="oidc"),
    )
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer signed-token"}
        assert client.get(f"/timeline?patient_id={patient_id}", headers=headers).status_code == 200
        assert client.get(
            "/timeline?patient_id=22222222-2222-2222-2222-222222222222",
            headers=headers,
        ).status_code == 403


def test_production_redis_limiter_requires_configuration(monkeypatch) -> None:
    monkeypatch.setenv("SMRITI_ENV", "production")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("RATE_LIMIT_BACKEND", raising=False)
    with pytest.raises(RuntimeError, match="Invalid production configuration"):
        with TestClient(app):
            pass


def test_token_mode_is_single_tenant_outside_development(monkeypatch) -> None:
    rate_limiter._events.clear()
    patient_id = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setenv("SMRITI_ENV", "staging")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("SMRITI_API_TOKEN", "test-token")
    monkeypatch.setenv("SMRITI_TOKEN_PATIENT_ID", patient_id)
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer test-token"}
        assert client.get(f"/timeline?patient_id={patient_id}", headers=headers).status_code == 200
        assert client.get(
            "/timeline?patient_id=22222222-2222-2222-2222-222222222222",
            headers=headers,
        ).status_code == 403
