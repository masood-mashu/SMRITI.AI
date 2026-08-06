from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.security import AuthContext, rate_limiter


def test_mcp_lists_tools_and_calls_context_tool(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    patient_id = str(uuid4())
    with TestClient(app) as client:
        listed = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert listed.status_code == 200
        assert {tool["name"] for tool in listed.json()["result"]["tools"]} == {
            "get_current_facts",
            "get_emergency_facts",
            "get_contradictions",
        }

        called = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_current_facts", "arguments": {"patient_id": patient_id}},
            },
        )
        assert called.status_code == 200
        assert called.json()["result"]["structuredContent"] == {"facts": []}


def test_mcp_rejects_unknown_method() -> None:
    with TestClient(app) as client:
        response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "nope"})
        assert response.json()["error"]["code"] == -32601


def test_mcp_enforces_oidc_patient_binding(monkeypatch) -> None:
    rate_limiter._events.clear()
    owned = "55555555-5555-5555-5555-555555555555"
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("OIDC_AUDIENCE", "smriti-api")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setattr(
        "backend.app.security._oidc_context",
        lambda token, settings: AuthContext(subject="user-1", patient_id=owned, mode="oidc"),
    )
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers={"Authorization": "Bearer signed-token"},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_current_facts",
                    "arguments": {"patient_id": "66666666-6666-6666-6666-666666666666"},
                },
            },
        )
        assert response.status_code == 403
