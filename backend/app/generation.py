"""Provider boundary for generated agent outputs."""

from dataclasses import dataclass
import os
import time
from collections.abc import Iterator
from typing import Any, Protocol


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
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            from google import genai

            if not self.project:
                raise GenerationError("GOOGLE_CLOUD_PROJECT is required for Vertex output generation")
            self._client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
            )
        return self._client

    def generate(self, *, prompt: str) -> GenerationResult:
        if self._client is None:
            from google.genai import types

            config = types.GenerateContentConfig(temperature=0.2)
        else:
            config = {"temperature": 0.2}
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
                time.sleep(0.2 * (2**attempt))
            except Exception as exc:
                raise GenerationError(f"Vertex output generation failed: {exc}") from exc
        if response is None:
            raise GenerationError("Vertex output generation returned no response")
        return GenerationResult(text=response.text.strip(), provider="vertex-gemini")

    def stream(self, *, prompt: str) -> Iterator[str]:
        if self._client is None:
            from google.genai import types

            config = types.GenerateContentConfig(temperature=0.2)
        else:
            config = {"temperature": 0.2}
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
                time.sleep(0.2 * (2**attempt))
            except Exception as exc:
                raise GenerationError(f"Vertex streaming failed: {exc}") from exc


def get_vertex_generator(*, model_env: str, default_model: str) -> VertexTextGenerator | None:
    if os.getenv("OUTPUT_PROVIDER", "stub").lower() != "vertex":
        return None
    return VertexTextGenerator(model=os.getenv(model_env, default_model))
