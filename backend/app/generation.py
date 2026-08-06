"""Provider boundary for generated agent outputs."""

from dataclasses import dataclass
import os
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
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except GenerationError:
            raise
        except Exception as exc:
            raise GenerationError(f"Vertex output generation failed: {exc}") from exc
        return GenerationResult(text=response.text.strip(), provider="vertex-gemini")


def get_vertex_generator(*, model_env: str, default_model: str) -> VertexTextGenerator | None:
    if os.getenv("OUTPUT_PROVIDER", "stub").lower() != "vertex":
        return None
    return VertexTextGenerator(model=os.getenv(model_env, default_model))
