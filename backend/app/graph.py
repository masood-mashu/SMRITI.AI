"""LangGraph skeleton for Smriti's five-agent pipeline."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class SmritiState(TypedDict, total=False):
    patient_id: str
    filename: str
    content_type: str
    report_bytes: bytes
    target_language: str
    extracted_facts: list[dict[str, Any]]
    memory_updated: bool
    explanation: str
    doctor_brief: str
    emergency_card: str
    translation: str


def report_understanding_agent(state: SmritiState) -> dict[str, Any]:
    """Stub: multimodal extraction and plain-language explanation."""
    return {"extracted_facts": [], "explanation": f"Report understanding stub received {state.get('filename', 'file')}"}


def memory_agent(state: SmritiState) -> dict[str, Any]:
    """Stub: append-only merge into Postgres-backed health memory."""
    return {"memory_updated": False}


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
