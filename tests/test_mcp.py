from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app


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
