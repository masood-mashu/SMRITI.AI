"""PII scrubbing provider boundary for report ingestion."""

from dataclasses import dataclass
import re
from typing import Protocol


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


def get_pii_scrubber() -> PiiScrubber:
    return GemmaPiiScrubber()
