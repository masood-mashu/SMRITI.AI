"""Optional hackathon-stack integration boundaries.

The local implementations are usable now; cloud-backed providers are opt-in
and fail explicitly rather than silently pretending to be connected.
"""

from datetime import datetime, timezone
import os
from typing import Any, Protocol
from uuid import UUID

import requests

from sqlmodel import Session

from .repositories import get_current_facts, get_emergency_facts, get_patient_contradictions


class IntegrationNotConfigured(RuntimeError):
    pass


class PromptRegistry(Protocol):
    def get(self, name: str) -> str:
        """Return a named, versioned prompt template."""


LOCAL_PROMPTS = {
    "doctor_brief": (
        "Create a concise clinician-facing summary from patient-owned memory. "
        "Organize recorded facts, call out contradictions for review, and do not diagnose "
        "or recommend treatment.\n\n{context}"
    ),
    "emergency_card": (
        "Format these emergency-relevant facts as a compact information card. "
        "Do not infer, diagnose, or recommend treatment.\n\n{context}"
    ),
    "language": (
        "Translate this patient-owned health summary into {language}. Preserve facts exactly, "
        "use plain language, and do not diagnose or recommend treatment.\n\n{context}"
    ),
}


class LocalPromptRegistry:
    def get(self, name: str) -> str:
        try:
            return LOCAL_PROMPTS[name]
        except KeyError as exc:
            raise IntegrationNotConfigured(f"Unknown local prompt: {name}") from exc


class AIStudioPromptRegistry:
    """HTTP adapter for a deployed AI Studio prompt registry facade.

    The registry URL is deployment-specific; the adapter accepts responses in
    the form ``{"prompt": "..."}`` or ``{"template": "..."}``.
    """

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def get(self, name: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            response = requests.get(f"{self.base_url}/prompts/{name}", headers=headers, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            prompt = payload.get("prompt") or payload.get("template")
            if not isinstance(prompt, str) or not prompt:
                raise IntegrationNotConfigured(f"AI Studio prompt '{name}' response has no prompt text")
            return prompt
        except IntegrationNotConfigured:
            raise
        except Exception as exc:
            raise IntegrationNotConfigured(f"AI Studio prompt '{name}' request failed: {exc}") from exc


def get_prompt_registry() -> PromptRegistry:
    provider = os.getenv("PROMPT_PROVIDER", "local").lower()
    if provider == "local":
        return LocalPromptRegistry()
    if provider == "ai_studio":
        base_url = os.getenv("AI_STUDIO_PROMPT_URL")
        if not base_url:
            raise IntegrationNotConfigured("AI_STUDIO_PROMPT_URL is required for PROMPT_PROVIDER=ai_studio")
        return AIStudioPromptRegistry(base_url, os.getenv("AI_STUDIO_API_KEY"))
    raise IntegrationNotConfigured(f"Unsupported PROMPT_PROVIDER: {provider}")


class MCPContextGateway:
    """MCP-shaped context tool facade over the current SQLModel repositories.

    The methods and tool names are stable for a future JSON-RPC MCP server.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        patient_id = UUID(arguments["patient_id"])
        if name == "get_current_facts":
            facts = get_current_facts(self.session, patient_id)
        elif name == "get_emergency_facts":
            facts = get_emergency_facts(self.session, patient_id)
        elif name == "get_contradictions":
            return {
                "contradictions": [item.description for item in get_patient_contradictions(self.session, patient_id)]
            }
        else:
            raise IntegrationNotConfigured(f"Unknown MCP context tool: {name}")
        return {
            "facts": [
                {
                    "fact_type": fact.fact_type,
                    "fact_key": fact.fact_key,
                    "fact_value": fact.fact_value,
                    "effective_date": fact.effective_date.isoformat(),
                    "is_emergency_relevant": fact.is_emergency_relevant,
                }
                for fact in facts
            ]
        }


class BigQueryAuditSink:
    """Opt-in sink for anonymized audit events and usage metadata."""

    def __init__(self, project: str, dataset: str, table: str, client: Any | None = None) -> None:
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise IntegrationNotConfigured("Install google-cloud-bigquery for BigQuery audit events") from exc
        self.client = client or bigquery.Client(project=project)
        self.table = f"{project}.{dataset}.{table}"

    def write(self, event: str, fields: dict[str, Any]) -> None:
        row = {
            "event": event,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        errors = self.client.insert_rows_json(self.table, [row])
        if errors:
            raise IntegrationNotConfigured(f"BigQuery audit insert failed: {errors}")


def get_audit_sink() -> BigQueryAuditSink | None:
    if os.getenv("AUDIT_SINK", "local").lower() != "bigquery":
        return None
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    dataset = os.getenv("BIGQUERY_DATASET")
    table = os.getenv("BIGQUERY_AUDIT_TABLE", "smriti_audit_events")
    if not project or not dataset:
        raise IntegrationNotConfigured("GOOGLE_CLOUD_PROJECT and BIGQUERY_DATASET are required for BigQuery")
    return BigQueryAuditSink(project, dataset, table)
