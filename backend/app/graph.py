"""LangGraph skeleton for Smriti's five-agent pipeline."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .db import session_scope
from .repositories import persist_report_and_facts


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
    persisted_fact_ids: list[str]
    contradiction_ids: list[str]
    explanation: str
    doctor_brief: str
    emergency_card: str
    translation: str


def report_understanding_agent(state: SmritiState) -> dict[str, Any]:
    """Stub: multimodal extraction and plain-language explanation."""
    return {"extracted_facts": [], "explanation": f"Report understanding stub received {state.get('filename', 'file')}"}


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
        )
        return {
            "memory_updated": True,
            "report_id": str(report.report_id),
            "persisted_fact_ids": [str(fact.fact_id) for fact in facts],
            "contradiction_ids": [str(item.contradiction_id) for item in contradictions],
        }


def doctor_brief_agent(state: SmritiState) -> dict[str, str]:
    """Stub: clinical brief and contradiction summary."""
    return {"doctor_brief": "Doctor Brief Agent stub"}


def emergency_agent(state: SmritiState) -> dict[str, str]:
    """Stub: emergency-relevant structured profile."""
    return {"emergency_card": "Emergency Agent stub"}


def language_agent(state: SmritiState) -> dict[str, str]:
    """Stub: plain-language and regional-language translation."""
    return {"translation": "Language Agent stub"}


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
