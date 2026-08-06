import pytest

from backend.app.extractor import (
    ExtractionError,
    FixtureExtractor,
    GeminiExtractorStub,
    ProviderConfigurationError,
    VertexGeminiExtractor,
)
from backend.app.privacy import GemmaPiiScrubber, RegexPiiScrubber


def test_fixture_and_gemini_provider_contracts() -> None:
    fixture = FixtureExtractor().extract(
        filename="fixture.pdf",
        content_type="application/pdf",
        content=b"synthetic",
    )
    gemini = GeminiExtractorStub().extract(
        filename="real.pdf",
        content_type="application/pdf",
        content=b"bytes",
    )
    assert fixture.provider == "fixture"
    assert len(fixture.facts) == 3
    assert gemini.provider == "gemini-stub"
    assert gemini.facts == []


def test_gemma_scrubber_uses_safe_text_fallback() -> None:
    content = b"Contact patient@example.com or +91 98765 43210"
    result = GemmaPiiScrubber(RegexPiiScrubber()).scrub(
        content=content,
        filename="note.txt",
        content_type="text/plain",
    )
    assert result.provider == "gemma-stub+regex-dev"
    assert result.redactions == 2
    assert b"patient@example.com" not in result.content
    assert b"98765" not in result.content


def test_vertex_gemini_adapter_parses_structured_response() -> None:
    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["model"] == "test-model"
            assert kwargs["contents"][1]["mime_type"] == "application/pdf"

            class Response:
                text = '{"facts":[{"fact_type":"allergy","fact_key":"Penicillin","fact_value":"Severe reaction","effective_date":"2026-01-15"}],"explanation":"Sample explanation"}'

            return Response()

    class FakeClient:
        models = FakeModels()

    result = VertexGeminiExtractor(model="test-model", client=FakeClient()).extract(
        filename="report.pdf",
        content_type="application/pdf",
        content=b"pdf-bytes",
    )
    assert result.provider == "vertex-gemini"
    assert result.facts[0]["effective_date"].isoformat() == "2026-01-15"


def test_vertex_gemini_adapter_rejects_unsafe_fact_shape() -> None:
    class FakeModels:
        def generate_content(self, **kwargs):
            class Response:
                text = '{"facts":[{"fact_type":"diagnosis","fact_key":"x","fact_value":"y","effective_date":"2026-01-15"}]}'

            return Response()

    class FakeClient:
        models = FakeModels()

    with pytest.raises(ExtractionError, match="invalid extraction JSON"):
        VertexGeminiExtractor(client=FakeClient()).extract(
            filename="report.pdf",
            content_type="application/pdf",
            content=b"pdf-bytes",
        )


def test_vertex_gemini_adapter_reports_missing_project() -> None:
    with pytest.raises(ProviderConfigurationError, match="GOOGLE_CLOUD_PROJECT"):
        VertexGeminiExtractor(project=None).extract(
            filename="report.pdf",
            content_type="application/pdf",
            content=b"pdf-bytes",
        )
