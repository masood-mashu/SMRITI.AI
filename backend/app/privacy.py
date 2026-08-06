"""PII scrubbing provider boundary for report ingestion."""

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Protocol


@dataclass(frozen=True)
class ScrubResult:
    content: bytes
    redactions: int
    provider: str


class PiiScrubber(Protocol):
    def scrub(self, *, content: bytes, filename: str, content_type: str) -> ScrubResult:
        """Return content safe to pass to the report extractor."""


class RegexPiiScrubber:
    """Development fallback for text uploads; binary reports pass through."""

    _patterns = (
        re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        re.compile(rb"(?<!\d)(?:\+?\d[\s-]?){10,13}(?!\d)"),
    )

    def scrub(self, *, content: bytes, filename: str, content_type: str) -> ScrubResult:
        if not (content_type.startswith("text/") or filename.lower().endswith((".txt", ".csv"))):
            return ScrubResult(content=content, redactions=0, provider="regex-dev")
        scrubbed = content
        redactions = 0
        for pattern in self._patterns:
            scrubbed, count = pattern.subn(b"[REDACTED]", scrubbed)
            redactions += count
        return ScrubResult(content=scrubbed, redactions=redactions, provider="regex-dev")


class GemmaPiiScrubber:
    """Gemma adapter seam; delegates locally until the Cloud Run model is wired."""

    def __init__(self, fallback: PiiScrubber | None = None) -> None:
        self.fallback = fallback or RegexPiiScrubber()

    def scrub(self, *, content: bytes, filename: str, content_type: str) -> ScrubResult:
        result = self.fallback.scrub(
            content=content,
            filename=filename,
            content_type=content_type,
        )
        return ScrubResult(
            content=result.content,
            redactions=result.redactions,
            provider="gemma-stub+" + result.provider,
        )


class VertexGemmaPiiScrubber:
    """Opt-in Gemma redaction adapter using the Google Gen AI Vertex client."""

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
        client: Any | None = None,
        fallback: PiiScrubber | None = None,
    ) -> None:
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.model = model or os.getenv("GEMMA_PII_MODEL", "gemma-3-27b-it")
        self._client = client
        self.fallback = fallback or RegexPiiScrubber()

    @property
    def client(self) -> Any:
        if self._client is None:
            from google import genai

            if not self.project:
                raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Vertex Gemma")
            self._client = genai.Client(vertexai=True, project=self.project, location=self.location)
        return self._client

    def scrub(self, *, content: bytes, filename: str, content_type: str) -> ScrubResult:
        # Gemma is used for text redaction here; binary reports remain protected
        # by the deterministic fallback until a multimodal deployment is set up.
        if not (content_type.startswith("text/") or filename.lower().endswith((".txt", ".csv"))):
            result = self.fallback.scrub(content=content, filename=filename, content_type=content_type)
            return ScrubResult(result.content, result.redactions, "vertex-gemma-bypass+" + result.provider)
        prompt = (
            "Redact names, email addresses, phone numbers, addresses, dates of birth, and patient IDs "
            "from this medical text. Preserve all non-PII text exactly. Return JSON only with keys "
            "content and redactions (integer).\n\n" + content.decode("utf-8", errors="replace")
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0},
            )
            payload = json.loads(response.text)
            redacted = str(payload["content"]).encode("utf-8")
            redactions = int(payload["redactions"])
        except Exception as exc:
            raise RuntimeError(f"Vertex Gemma PII request failed: {exc}") from exc
        return ScrubResult(redacted, redactions, "vertex-gemma")


def get_pii_scrubber() -> PiiScrubber:
    provider = os.getenv("PII_PROVIDER", "gemma_stub").lower()
    if provider in {"regex", "regex_dev"}:
        return RegexPiiScrubber()
    if provider in {"gemma_stub", "stub"}:
        return GemmaPiiScrubber()
    if provider in {"vertex_gemma", "gemma"}:
        return VertexGemmaPiiScrubber()
    raise RuntimeError(f"Unsupported PII_PROVIDER: {provider}")
