"""Google ADK-compatible health-memory tools and registration helper."""

from uuid import UUID

from .db import session_scope
from .repositories import get_current_facts, get_emergency_facts, get_patient_contradictions


def get_adk_tools() -> list[object]:
    """Return ADK FunctionTool wrappers when the optional ADK extra is installed.

    ADK accepts plain Python functions; FunctionTool makes the integration
    explicit for applications that build agents programmatically.
    """
    try:
        from google.adk.tools import FunctionTool
    except ImportError as exc:
        raise RuntimeError("Install the 'adk' extra to register Google ADK tools") from exc
    return [
        FunctionTool(get_current_health_facts),
        FunctionTool(get_emergency_health_facts),
        FunctionTool(get_health_contradictions),
    ]


def get_current_health_facts(patient_id: str) -> list[dict]:
    with session_scope() as session:
        return [
            {"fact_key": fact.fact_key, "fact_value": fact.fact_value, "fact_type": fact.fact_type}
            for fact in get_current_facts(session, UUID(patient_id))
        ]


def get_emergency_health_facts(patient_id: str) -> list[dict]:
    with session_scope() as session:
        return [
            {"fact_key": fact.fact_key, "fact_value": fact.fact_value, "fact_type": fact.fact_type}
            for fact in get_emergency_facts(session, UUID(patient_id))
        ]


def get_health_contradictions(patient_id: str) -> list[str]:
    with session_scope() as session:
        return [item.description for item in get_patient_contradictions(session, UUID(patient_id))]
