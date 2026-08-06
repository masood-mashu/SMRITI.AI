"""Provider boundary for report understanding.

The production implementation will call Gemini through Vertex AI. Keeping the
contract here lets the graph and tests remain independent of an LLM SDK.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class ExtractionResult:
    facts: list[dict[str, Any]]
    explanation: str
    provider: str


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


def get_extractor(*, use_fixture: bool) -> ReportExtractor:
    return FixtureExtractor() if use_fixture else GeminiExtractorStub()


def extract_report(*, filename: str, use_fixture: bool = False) -> dict[str, Any]:
    """Backward-compatible helper for callers not yet using the provider API."""
    result = get_extractor(use_fixture=use_fixture).extract(
        filename=filename,
        content_type="application/octet-stream",
        content=b"",
    )
    return {"facts": result.facts, "explanation": result.explanation, "provider": result.provider}

