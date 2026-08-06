from backend.app.extractor import FixtureExtractor, GeminiExtractorStub
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

