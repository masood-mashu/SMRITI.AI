from datetime import date
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

from backend.app.integrations import (
    BigQueryAuditSink,
    AIStudioPromptRegistry,
    IntegrationNotConfigured,
    LocalPromptRegistry,
    MCPContextGateway,
)
from backend.app.repositories import persist_report_and_facts


def test_local_prompt_registry_has_guardrail_prompts() -> None:
    registry = LocalPromptRegistry()
    assert "do not diagnose" in registry.get("doctor_brief").lower()
    assert "{language}" in registry.get("language")


def test_mcp_context_gateway_exposes_current_and_emergency_tools() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    patient_id = uuid4()
    with Session(engine) as session:
        persist_report_and_facts(
            session,
            patient_id=patient_id,
            source_type="prescription",
            raw_extraction=None,
            extracted_facts=[
                {
                    "fact_type": "allergy",
                    "fact_key": "Penicillin",
                    "fact_value": "Severe reaction",
                    "effective_date": date(2026, 8, 6),
                    "is_emergency_relevant": True,
                }
            ],
        )
        session.commit()
        gateway = MCPContextGateway(session)
        current = gateway.call_tool("get_current_facts", {"patient_id": str(patient_id)})
        emergency = gateway.call_tool("get_emergency_facts", {"patient_id": str(patient_id)})
        assert current["facts"][0]["fact_key"] == "Penicillin"
        assert emergency["facts"][0]["is_emergency_relevant"] is True


def test_unknown_mcp_tool_is_rejected() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        with pytest.raises(IntegrationNotConfigured):
            MCPContextGateway(session).call_tool("unknown", {"patient_id": str(uuid4())})


def test_bigquery_sink_writes_anonymized_event_with_injected_client() -> None:
    class FakeClient:
        def __init__(self):
            self.calls = []

        def insert_rows_json(self, table, rows):
            self.calls.append((table, rows))
            return []

    client = FakeClient()
    sink = BigQueryAuditSink("project", "dataset", "events", client=client)
    sink.write("http_request", {"status_code": 200, "patient_id": "not-included-by-callers"})
    table, rows = client.calls[0]
    assert table == "project.dataset.events"
    assert rows[0]["event"] == "http_request"
    assert rows[0]["status_code"] == 200


def test_ai_studio_prompt_registry_reads_configured_prompt(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"prompt": "configured prompt {context}"}

    monkeypatch.setattr("backend.app.integrations.requests.get", lambda *args, **kwargs: FakeResponse())
    registry = AIStudioPromptRegistry("https://prompts.example", "test-key")
    assert registry.get("doctor_brief") == "configured prompt {context}"
