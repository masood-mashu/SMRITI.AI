"""Provider boundary for report understanding.

The production implementation will call Gemini through Vertex AI. Keeping the
contract here lets the graph and tests remain independent of an LLM SDK.
"""

from dataclasses import dataclass
from datetime import date
import os
import time
import random
import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from .grok import GrokClient, GrokRequestError
from .nvidia import NvidiaClient, NvidiaRequestError


@dataclass(frozen=True)
class ExtractionResult:
    facts: list[dict[str, Any]]
    explanation: str
    provider: str


class ExtractionError(RuntimeError):
    """Raised when a provider response cannot be trusted as structured data."""


class ProviderConfigurationError(ExtractionError):
    """Raised when a configured provider cannot be initialized."""


class ExtractedFact(BaseModel):
    fact_type: Literal[
        "condition",
        "medication",
        "allergy",
        "lab_value",
        "procedure",
        "vaccination",
    ]
    fact_key: str = Field(min_length=1)
    fact_value: str = Field(min_length=1)
    unit: str | None = None
    status: Literal["active", "resolved", "discontinued"] = "active"
    is_emergency_relevant: bool = False
    effective_date: date
    confidence: float | None = Field(default=None, ge=0, le=1)


class ExtractionPayload(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)
    explanation: str = ""


class ReportExtractor(Protocol):
    def extract(self, *, filename: str, content_type: str, content: bytes) -> ExtractionResult:
        """Extract structured facts and an explanation from a report."""


class FixtureExtractor:
    """Synthetic, deterministic profile for local demos and tests."""

    def extract(self, *, filename: str, content_type: str, content: bytes) -> ExtractionResult:
        return ExtractionResult(
            facts=[
                {
                    "fact_type": "condition",
                    "fact_key": "Type 2 diabetes",
                    "fact_value": "Recorded in synthetic demo profile",
                    "effective_date": date(2026, 1, 15),
                    "is_emergency_relevant": True,
                    "confidence": 0.99,
                },
                {
                    "fact_type": "medication",
                    "fact_key": "Metformin",
                    "fact_value": "500 mg",
                    "unit": "mg",
                    "effective_date": date(2026, 1, 15),
                    "is_emergency_relevant": True,
                    "confidence": 0.99,
                },
                {
                    "fact_type": "allergy",
                    "fact_key": "Penicillin",
                    "fact_value": "Severe reaction",
                    "effective_date": date(2026, 1, 15),
                    "is_emergency_relevant": True,
                    "confidence": 0.99,
                },
            ],
            explanation="Synthetic development fixture: a sample longitudinal health profile was extracted.",
            provider="fixture",
        )


class GeminiExtractorStub:
    """Vertex AI/Gemini adapter seam; no network or LLM call yet."""

    def extract(self, *, filename: str, content_type: str, content: bytes) -> ExtractionResult:
        return ExtractionResult(
            facts=[],
            explanation=(
                f"Gemini extraction stub received {filename}; "
                "Vertex AI integration is not configured yet."
            ),
            provider="gemini-stub",
        )


class VertexGeminiExtractor:
    """Gemini multimodal extractor using AI Studio or Vertex AI."""

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.1-pro")
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            from google import genai

            if self.api_key:
                self._client = genai.Client(api_key=self.api_key)
            else:
                if not self.project:
                    raise ProviderConfigurationError(
                        "GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT is required for Gemini"
                    )
                self._client = genai.Client(vertexai=True, project=self.project, location=self.location)
        return self._client

    def extract(self, *, filename: str, content_type: str, content: bytes) -> ExtractionResult:
        prompt = """You are Smriti's medical report understanding agent.
Extract only facts explicitly present in the report. Do not diagnose, recommend
treatment, or infer missing information. Return JSON with this exact shape:
{"facts":[{"fact_type":"condition|medication|allergy|lab_value|procedure|vaccination",
"fact_key":"normalized name","fact_value":"value","unit":null,
"status":"active|resolved|discontinued","is_emergency_relevant":false,
"effective_date":"YYYY-MM-DD","confidence":0.0}],"explanation":"plain-language explanation"}
"""
        if self._client is None:
            from google.genai import types

            file_part = types.Part.from_bytes(data=content, mime_type=content_type)
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
                max_output_tokens=int(os.getenv("EXTRACTION_MAX_OUTPUT_TOKENS", "4096")),
            )
        else:
            file_part = {"data": content, "mime_type": content_type}
            config = {
                "response_mime_type": "application/json",
                "temperature": 0,
                "max_output_tokens": int(os.getenv("EXTRACTION_MAX_OUTPUT_TOKENS", "4096")),
            }

        response = None
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[prompt, file_part],
                    config=config,
                )
                break
            except ProviderConfigurationError:
                raise
            except (TimeoutError, ConnectionError) as exc:
                if attempt == 2:
                    raise ExtractionError(f"Vertex Gemini request failed after retries: {exc}") from exc
                time.sleep(random.uniform(0.15, 0.35) * (2**attempt))
            except Exception as exc:
                raise ExtractionError(f"Vertex Gemini request failed: {exc}") from exc
        if response is None:
            raise ExtractionError("Vertex Gemini request returned no response")
        return self._parse_response(response.text)

    def _parse_response(self, text: str) -> ExtractionResult:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            try:
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            except IndexError as exc:
                raise ExtractionError("Gemini returned an invalid markdown response") from exc
        try:
            payload = ExtractionPayload.model_validate_json(cleaned)
        except (ValidationError, ValueError) as exc:
            raise ExtractionError(f"Gemini returned invalid extraction JSON: {exc}") from exc
        return ExtractionResult(
            facts=[fact.model_dump() for fact in payload.facts],
            explanation=payload.explanation,
            provider="vertex-gemini",
        )


class GrokExtractor:
    """Text report extractor using the xAI chat completions API."""

    def __init__(self, *, client: GrokClient | None = None) -> None:
        self.client = client or GrokClient()

    def extract(self, *, filename: str, content_type: str, content: bytes) -> ExtractionResult:
        if not content_type.startswith("text/"):
            raise ExtractionError("Grok extraction currently supports text reports only")
        prompt = """Extract only facts explicitly present in this medical report. Do not diagnose,
recommend treatment, or infer missing information. Return JSON with this exact shape:
{"facts":[{"fact_type":"condition|medication|allergy|lab_value|procedure|vaccination",
"fact_key":"normalized name","fact_value":"value","unit":null,
"status":"active|resolved|discontinued","is_emergency_relevant":false,
"effective_date":"YYYY-MM-DD","confidence":0.0}],"explanation":"plain-language explanation"}
"""
        try:
            raw = self.client.complete(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content.decode("utf-8", errors="replace")},
                ],
                json_mode=True,
            )
            payload = ExtractionPayload.model_validate_json(raw)
        except GrokRequestError as exc:
            raise ExtractionError(str(exc)) from exc
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise ExtractionError(f"Grok returned invalid extraction JSON: {exc}") from exc
        return ExtractionResult(
            facts=[fact.model_dump() for fact in payload.facts],
            explanation=payload.explanation,
            provider="grok",
        )


class NvidiaExtractor:
    """Text report extractor using an NVIDIA hosted NIM endpoint."""

    def __init__(self, *, client: NvidiaClient | None = None) -> None:
        self.client = client or NvidiaClient()

    def extract(self, *, filename: str, content_type: str, content: bytes) -> ExtractionResult:
        if not content_type.startswith("text/"):
            raise ExtractionError("NVIDIA extraction currently supports text reports only")
        prompt = """Extract only facts explicitly present in this medical report. Do not diagnose,
recommend treatment, or infer missing information. Return JSON with this exact shape:
{"facts":[{"fact_type":"condition|medication|allergy|lab_value|procedure|vaccination",
"fact_key":"normalized name","fact_value":"value","unit":null,
"status":"active|resolved|discontinued","is_emergency_relevant":false,
"effective_date":"YYYY-MM-DD","confidence":0.0}],"explanation":"plain-language explanation"}
"""
        try:
            raw = self.client.complete(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content.decode("utf-8", errors="replace")},
                ],
                json_mode=True,
            )
            payload = ExtractionPayload.model_validate_json(raw)
        except NvidiaRequestError as exc:
            raise ExtractionError(str(exc)) from exc
        except (ValidationError, ValueError) as exc:
            raise ExtractionError(f"NVIDIA returned invalid extraction JSON: {exc}") from exc
        return ExtractionResult(
            facts=[fact.model_dump() for fact in payload.facts],
            explanation=payload.explanation,
            provider="nvidia",
        )


def get_extractor(*, use_fixture: bool) -> ReportExtractor:
    if use_fixture:
        return FixtureExtractor()
    if os.getenv("EXTRACTION_PROVIDER", "stub").lower() in {"gemini", "ai_studio", "vertex"}:
        return VertexGeminiExtractor()
    if os.getenv("EXTRACTION_PROVIDER", "stub").lower() in {"grok", "xai"}:
        return GrokExtractor()
    if os.getenv("EXTRACTION_PROVIDER", "stub").lower() in {"nvidia", "nim"}:
        return NvidiaExtractor()
    raise ProviderConfigurationError(
        "Real report extraction is not configured; set EXTRACTION_PROVIDER=gemini, grok, nvidia, or vertex, or use fixture mode in development"
    )


def extract_report(*, filename: str, use_fixture: bool = False) -> dict[str, Any]:
    """Backward-compatible helper for callers not yet using the provider API."""
    result = get_extractor(use_fixture=use_fixture).extract(
        filename=filename,
        content_type="application/octet-stream",
        content=b"",
    )
    return {"facts": result.facts, "explanation": result.explanation, "provider": result.provider}
