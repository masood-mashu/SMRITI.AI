"""Run one explicit Vertex Gemini extraction against a local report file.

Usage:
    python scripts/vertex_smoke.py path/to/report.pdf

Requires Application Default Credentials and GOOGLE_CLOUD_PROJECT. This script
does not run as part of the app or test suite.
"""

import argparse
import mimetypes
from pathlib import Path

from backend.app.extractor import VertexGeminiExtractor


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test Vertex Gemini report extraction")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    content_type = mimetypes.guess_type(args.report.name)[0] or "application/octet-stream"
    result = VertexGeminiExtractor().extract(
        filename=args.report.name,
        content_type=content_type,
        content=args.report.read_bytes(),
    )
    print(f"provider={result.provider}")
    print(f"facts={len(result.facts)}")
    for fact in result.facts:
        print(f"- {fact['fact_type']}: {fact['fact_key']} = {fact['fact_value']}")
    print(f"explanation={result.explanation}")


if __name__ == "__main__":
    main()
