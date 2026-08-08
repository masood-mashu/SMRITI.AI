"""Provider boundary for generated agent outputs."""

from dataclasses import dataclass
import os
import time
import random
from collections.abc import Iterator
from typing import Any, Protocol

from .grok import GrokClient, GrokRequestError
from .nvidia import NvidiaClient, NvidiaRequestError


class GenerationError(RuntimeError):
    """Raised when an output provider cannot complete a generation request."""


@dataclass(frozen=True)
class GenerationResult:
    text: str
    provider: str


class TextGenerator(Protocol):
    def generate(self, *, prompt: str) -> GenerationResult:
        """Generate a safe, non-diagnostic response from a prompt."""

    def stream(self, *, prompt: str) -> Iterator[str]:
        """Yield safe, non-diagnostic response chunks."""


class VertexTextGenerator:
    def __init__(
        self,
        *,
        model: str,
        project: str | None = None,
        location: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "global")
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
                    raise GenerationError(
                        "GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT is required for Gemini output generation"
                    )
                self._client = genai.Client(vertexai=True, project=self.project, location=self.location)
        return self._client

    def generate(self, *, prompt: str) -> GenerationResult:
        if self._client is None:
            from google.genai import types

            config = types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=int(os.getenv("OUTPUT_MAX_OUTPUT_TOKENS", "2048")),
            )
        else:
            config = {
                "temperature": 0.2,
                "max_output_tokens": int(os.getenv("OUTPUT_MAX_OUTPUT_TOKENS", "2048")),
            }
        response = None
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                break
            except GenerationError:
                raise
            except (TimeoutError, ConnectionError) as exc:
                if attempt == 2:
                    raise GenerationError(f"Vertex output generation failed after retries: {exc}") from exc
                time.sleep(random.uniform(0.15, 0.35) * (2**attempt))
            except Exception as exc:
                raise GenerationError(f"Vertex output generation failed: {exc}") from exc
        if response is None:
            raise GenerationError("Vertex output generation returned no response")
        return GenerationResult(text=response.text.strip(), provider="vertex-gemini")

    def stream(self, *, prompt: str) -> Iterator[str]:
        if self._client is None:
            from google.genai import types

            config = types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=int(os.getenv("OUTPUT_MAX_OUTPUT_TOKENS", "2048")),
            )
        else:
            config = {
                "temperature": 0.2,
                "max_output_tokens": int(os.getenv("OUTPUT_MAX_OUTPUT_TOKENS", "2048")),
            }
        for attempt in range(3):
            try:
                chunks = self.client.models.generate_content_stream(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                for chunk in chunks:
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        yield text
                return
            except GenerationError:
                raise
            except (TimeoutError, ConnectionError) as exc:
                if attempt == 2:
                    raise GenerationError(f"Vertex streaming failed after retries: {exc}") from exc
                time.sleep(random.uniform(0.15, 0.35) * (2**attempt))
            except Exception as exc:
                raise GenerationError(f"Vertex streaming failed: {exc}") from exc


class GrokTextGenerator:
    """Text generator using the xAI chat completions API."""

    def __init__(self, *, model: str | None = None, client: GrokClient | None = None) -> None:
        self.client = client or GrokClient(model=model)

    def generate(self, *, prompt: str) -> GenerationResult:
        try:
            text = self.client.complete(
                messages=[
                    {"role": "system", "content": "You are a careful health-memory assistant. Do not diagnose or recommend treatment."},
                    {"role": "user", "content": prompt},
                ]
            )
        except GrokRequestError as exc:
            raise GenerationError(str(exc)) from exc
        return GenerationResult(text=text, provider="grok")

    def stream(self, *, prompt: str):
        # The graph supports streaming, but the static frontend uses the
        # non-streaming endpoints. Keep this method contract-safe for callers.
        yield self.generate(prompt=prompt).text


class NvidiaTextGenerator:
    """Text generator using an NVIDIA hosted NIM endpoint."""

    def __init__(self, *, model: str | None = None, client: NvidiaClient | None = None) -> None:
        self.client = client or NvidiaClient(model=model)

    def generate(self, *, prompt: str) -> GenerationResult:
        try:
            text = self.client.complete(
                messages=[
                    {"role": "system", "content": "You are a careful health-memory assistant. Do not diagnose or recommend treatment."},
                    {"role": "user", "content": prompt},
                ]
            )
        except NvidiaRequestError as exc:
            raise GenerationError(str(exc)) from exc
        return GenerationResult(text=text, provider="nvidia")

    def stream(self, *, prompt: str):
        yield self.generate(prompt=prompt).text


def get_vertex_generator(*, model_env: str, default_model: str) -> VertexTextGenerator | None:
    provider = os.getenv("OUTPUT_PROVIDER", "stub").lower()
    if provider in {"grok", "xai"}:
        return GrokTextGenerator(model=os.getenv("GROK_MODEL", default_model))
    if provider in {"nvidia", "nim"}:
        return NvidiaTextGenerator(model=os.getenv("NVIDIA_MODEL", default_model))
    if provider not in {"gemini", "ai_studio", "vertex"}:
        return None
    return VertexTextGenerator(model=os.getenv(model_env, default_model))
