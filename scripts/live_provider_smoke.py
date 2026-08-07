"""Exercise the live Vertex Gemini extraction, Gemma PII, and output paths.

This uses synthetic text only. It requires Application Default Credentials,
GOOGLE_CLOUD_PROJECT, Vertex API access, and billing.
"""

from __future__ import annotations

from backend.app.extractor import VertexGeminiExtractor
from backend.app.generation import VertexTextGenerator
from backend.app.privacy import VertexGemmaPiiScrubber


SYNTHETIC = b"Synthetic patient Alex Example, alex@example.test, takes metformin 500 mg."


def main() -> int:
    scrubbed = VertexGemmaPiiScrubber().scrub(
        content=SYNTHETIC,
        filename="synthetic.txt",
        content_type="text/plain",
    )
    extraction = VertexGeminiExtractor().extract(
        filename="synthetic.txt",
        content_type="text/plain",
        content=scrubbed.content,
    )
    generation = VertexTextGenerator(
        model="gemini-3.5-flash",
    ).generate(
        prompt=(
            "Summarize these synthetic recorded facts in one sentence. Do not diagnose or recommend treatment. "
            + repr(extraction.facts)
        )
    )
    print(f"pii_provider={scrubbed.provider} redactions={scrubbed.redactions}")
    print(f"extraction_provider={extraction.provider} facts={len(extraction.facts)}")
    print(f"output_provider={generation.provider} chars={len(generation.text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
