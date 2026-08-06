"""LangGraph skeleton for Smriti's five-agent pipeline."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class SmritiState(TypedDict, total=False):
    patient_id: str
    filename: str
    content_type: str
    report_bytes: bytes
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


def build_graph():
    graph = StateGraph(SmritiState)
    graph.add_node("report_understanding", report_understanding_agent)
    graph.add_node("memory", memory_agent)
    graph.add_node("doctor_brief", doctor_brief_agent)
    graph.add_node("emergency", emergency_agent)
    graph.add_node("language", language_agent)
    graph.add_edge(START, "report_understanding")
    graph.add_edge("report_understanding", "memory")
    graph.add_edge("memory", "doctor_brief")
    graph.add_edge("memory", "emergency")
    graph.add_edge("memory", "language")
    graph.add_edge("doctor_brief", END)
    graph.add_edge("emergency", END)
    graph.add_edge("language", END)
    return graph.compile()


smriti_graph = build_graph()

