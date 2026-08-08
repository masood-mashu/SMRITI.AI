import pytest

from backend.app.extractor import (
    ExtractionError,
    FixtureExtractor,
    GeminiExtractorStub,
    ProviderConfigurationError,
    VertexGeminiExtractor,
    GrokExtractor,
    get_extractor,
    NvidiaExtractor,
)
from backend.app.privacy import GemmaPiiScrubber, PrivacyPolicyError, RegexPiiScrubber, VertexGemmaPiiScrubber
from backend.app.generation import GenerationError, VertexTextGenerator, get_vertex_generator
from backend.app.config import validate_production_settings
from backend.app.grok import GrokClient
from backend.app.nvidia import NvidiaClient


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


def test_gemini_provider_selection_is_server_side(monkeypatch) -> None:
    monkeypatch.setenv("EXTRACTION_PROVIDER", "gemini")
    monkeypatch.setenv("OUTPUT_PROVIDER", "gemini")
    assert isinstance(get_extractor(use_fixture=False), VertexGeminiExtractor)
    assert get_vertex_generator(model_env="DOCTOR_BRIEF_MODEL", default_model="test-model") is not None


def test_grok_extractor_parses_structured_response() -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"facts": [], "explanation": "ok"}'}}]}

    class FakeSession:
        def post(self, *args, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["json"]["response_format"] == {"type": "json_object"}
            return FakeResponse()

    result = GrokExtractor(client=GrokClient(api_key="test-key", session=FakeSession())).extract(
        filename="report.txt",
        content_type="text/plain",
        content=b"Synthetic report",
    )
    assert result.provider == "grok"
    assert result.facts == []


def test_nvidia_extractor_parses_structured_response() -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"facts": [], "explanation": "ok"}'}}]}

    class FakeSession:
        def post(self, *args, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["json"]["model"] == "openai/gpt-oss-20b"
            return FakeResponse()

    result = NvidiaExtractor(client=NvidiaClient(api_key="test-key", session=FakeSession())).extract(
        filename="report.txt",
        content_type="text/plain",
        content=b"Synthetic report",
    )
    assert result.provider == "nvidia"
    assert result.facts == []


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


def test_strict_pii_mode_rejects_unscrubbed_binary_uploads() -> None:
    with pytest.raises(PrivacyPolicyError):
        RegexPiiScrubber(strict=True).scrub(
            content=b"pdf-bytes",
            filename="report.pdf",
            content_type="application/pdf",
        )


def test_vertex_gemma_scrubber_parses_redaction_response() -> None:
    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["model"] == "test-gemma"

            class Response:
                text = '{"content":"Call [REDACTED]", "redactions":1}'

            return Response()

    class FakeClient:
        models = FakeModels()

    result = VertexGemmaPiiScrubber(model="test-gemma", client=FakeClient()).scrub(
        content=b"Call patient@example.com",
        filename="note.txt",
        content_type="text/plain",
    )
    assert result.provider == "vertex-gemma"
    assert result.content == b"Call [REDACTED]"
    assert result.redactions == 1


def test_vertex_gemini_adapter_parses_structured_response() -> None:
    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["model"] == "test-model"
            assert kwargs["contents"][1]["mime_type"] == "application/pdf"
            assert kwargs["config"]["max_output_tokens"] == 4096

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


def test_vertex_gemini_adapter_wraps_request_errors() -> None:
    class FakeModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("billing disabled")

    class FakeClient:
        models = FakeModels()

    with pytest.raises(ExtractionError, match="Vertex Gemini request failed"):
        VertexGeminiExtractor(client=FakeClient()).extract(
            filename="report.pdf",
            content_type="application/pdf",
            content=b"pdf-bytes",
        )


def test_vertex_text_generator_uses_injected_client() -> None:
    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["model"] == "test-model"
            assert kwargs["config"]["max_output_tokens"] == 2048

            class Response:
                text = "Safe generated summary"

            return Response()

    class FakeClient:
        models = FakeModels()

    result = VertexTextGenerator(model="test-model", client=FakeClient()).generate(
        prompt="Summarize these recorded facts."
    )
    assert result.provider == "vertex-gemini"
    assert result.text == "Safe generated summary"


def test_vertex_text_generator_streams_injected_client() -> None:
    class FakeModels:
        def generate_content_stream(self, **kwargs):
            assert kwargs["model"] == "test-model"

            class Chunk:
                def __init__(self, text):
                    self.text = text

            return [Chunk("Safe "), Chunk("streamed summary")]

    class FakeClient:
        models = FakeModels()

    result = list(VertexTextGenerator(model="test-model", client=FakeClient()).stream(prompt="test"))
    assert result == ["Safe ", "streamed summary"]


def test_vertex_text_generator_wraps_request_errors() -> None:
    class FakeModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("billing disabled")

    class FakeClient:
        models = FakeModels()

    with pytest.raises(GenerationError, match="Vertex output generation failed"):
        VertexTextGenerator(model="test-model", client=FakeClient()).generate(prompt="test")


def test_production_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("SMRITI_ENV", "production")
    monkeypatch.setenv("SMRITI_VALIDATE_PRODUCTION", "true")
    for name in ("AUTH_ENABLED", "AUTH_MODE", "PHI_STRICT", "UPLOAD_SIGNATURE_CHECK", "STORAGE_PROVIDER", "RATE_LIMIT_BACKEND"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="Invalid production configuration"):
        validate_production_settings()
