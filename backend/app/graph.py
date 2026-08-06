"""LangGraph skeleton for Smriti's five-agent pipeline."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .db import session_scope
from .extractor import get_extractor
from .privacy import get_pii_scrubber
from .repositories import (
    get_current_facts,
    get_emergency_facts,
    get_patient_contradictions,
    persist_report_and_facts,
)


class SmritiState(TypedDict, total=False):
    patient_id: str
    filename: str
    content_type: str
    source_type: str
    report_bytes: bytes
    target_language: str
    extracted_facts: list[dict[str, Any]]
    memory_updated: bool
    report_id: str
    file_url: str
    use_fixture: bool
    pii_redactions: int
    pii_provider: str
    extraction_provider: str
    persisted_fact_ids: list[str]
    contradiction_ids: list[str]
    current_facts: list[dict[str, Any]]
    emergency_facts: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    explanation: str
    doctor_brief: str
    emergency_card: str
    translation: str


def report_understanding_agent(state: SmritiState) -> dict[str, Any]:
    """Development extractor boundary; Gemini will replace this implementation."""
    scrubbed = get_pii_scrubber().scrub(
        content=state.get("report_bytes", b""),
        filename=state.get("filename", "file"),
        content_type=state.get("content_type", "application/octet-stream"),
    )
    extraction = get_extractor(use_fixture=state.get("use_fixture", False)).extract(
        filename=state.get("filename", "file"),
        content_type=state.get("content_type", "application/octet-stream"),
        content=scrubbed.content,
    )
    return {
        "extracted_facts": extraction.facts,
        "explanation": extraction.explanation,
        "pii_redactions": scrubbed.redactions,
        "pii_provider": scrubbed.provider,
        "extraction_provider": extraction.provider,
    }


def memory_agent(state: SmritiState) -> dict[str, Any]:
    """Persist the report and apply the append-only fact merge."""
    from uuid import UUID

    patient_id = UUID(state["patient_id"])
    with session_scope() as session:
        report, facts, contradictions = persist_report_and_facts(
            session,
            patient_id=patient_id,
            source_type=state.get("source_type", "other"),
            raw_extraction={"facts": state.get("extracted_facts", [])},
            extracted_facts=state.get("extracted_facts", []),
            file_url=state.get("file_url"),
        )
        return {
            "memory_updated": True,
            "report_id": str(report.report_id),
            "persisted_fact_ids": [str(fact.fact_id) for fact in facts],
            "contradiction_ids": [str(item.contradiction_id) for item in contradictions],
        }


def doctor_brief_agent(state: SmritiState) -> dict[str, str]:
    """Read current memory and format a non-diagnostic brief stub."""
    from uuid import UUID

    with session_scope() as session:
        facts = get_current_facts(session, UUID(state["patient_id"]))
        contradictions = get_patient_contradictions(session, UUID(state["patient_id"]))
    fact_lines = [f"- {fact.fact_key}: {fact.fact_value}" for fact in facts]
    contradiction_lines = [item.description for item in contradictions]
    brief = "Current health memory:\n" + ("\n".join(fact_lines) or "- No facts persisted yet.")
    if contradiction_lines:
        brief += "\nContradictions to review:\n- " + "\n- ".join(contradiction_lines)
    return {"doctor_brief": brief}


def emergency_agent(state: SmritiState) -> dict[str, str]:
    """Read only current facts marked emergency-relevant."""
    from uuid import UUID

    with session_scope() as session:
        facts = get_emergency_facts(session, UUID(state["patient_id"]))
    lines = [f"- {fact.fact_key}: {fact.fact_value}" for fact in facts]
    return {"emergency_card": "Emergency-relevant facts:\n" + ("\n".join(lines) or "- None recorded yet.")}


def language_agent(state: SmritiState) -> dict[str, str]:
    """Read current memory before the future translation implementation."""
    from uuid import UUID

    with session_scope() as session:
        facts = get_current_facts(session, UUID(state["patient_id"]))
    language = state.get("target_language", "en")
    return {"translation": f"Language Agent stub ({language}) using {len(facts)} current fact(s)."}


def build_ingestion_graph():
    graph = StateGraph(SmritiState)
    graph.add_node("report_understanding", report_understanding_agent)
    graph.add_node("memory", memory_agent)
    graph.add_edge(START, "report_understanding")
    graph.add_edge("report_understanding", "memory")
    graph.add_edge("memory", END)
    return graph.compile()


def build_output_graph(node_name: str, node):
    graph = StateGraph(SmritiState)
    graph.add_node(node_name, node)
    graph.add_edge(START, node_name)
    graph.add_edge(node_name, END)
    return graph.compile()


smriti_ingestion_graph = build_ingestion_graph()
doctor_brief_graph = build_output_graph("doctor_brief", doctor_brief_agent)
emergency_graph = build_output_graph("emergency", emergency_agent)
language_graph = build_output_graph("language", language_agent)
