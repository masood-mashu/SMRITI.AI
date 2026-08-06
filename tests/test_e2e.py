from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app


def test_patient_flow_upload_memory_mcp_and_outputs(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    patient_id = str(uuid4())
    with TestClient(app) as client:
        upload = client.post(
            f"/reports?patient_id={patient_id}&fixture=true",
            files={"file": ("synthetic.txt", b"synthetic", "text/plain")},
        )
        assert upload.status_code == 200
        assert upload.json()["graph"]["memory_updated"] is True

        timeline = client.get(f"/timeline?patient_id={patient_id}")
        assert timeline.status_code == 200
        assert len(timeline.json()["facts"]) == 3

        mcp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "facts",
                "method": "tools/call",
                "params": {"name": "get_current_facts", "arguments": {"patient_id": patient_id}},
            },
        )
        assert mcp.status_code == 200
        assert len(mcp.json()["result"]["structuredContent"]["facts"]) == 3

        brief = client.post(f"/brief?patient_id={patient_id}")
        emergency = client.post(f"/emergency?patient_id={patient_id}")
        translation = client.post(f"/translate?patient_id={patient_id}&language=hi")
        assert brief.status_code == emergency.status_code == translation.status_code == 200
        assert brief.json()["graph"]["doctor_brief_provider"] == "deterministic"
