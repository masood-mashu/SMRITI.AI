"""Small xAI/Grok REST client used by the provider adapters."""

from __future__ import annotations

import os
from typing import Any

import requests


class GrokRequestError(RuntimeError):
    """Raised when the xAI API cannot return a usable response."""


class GrokClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        session: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
        self.base_url = (base_url or os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")).rstrip("/")
        self.model = model or os.getenv("GROK_MODEL", "grok-4.5")
        self.timeout = timeout or float(os.getenv("API_TIMEOUT_SECONDS", "60"))
        self.session = session or requests

    def complete(self, *, messages: list[dict[str, str]], json_mode: bool = False) -> str:
        if not self.api_key:
            raise GrokRequestError("XAI_API_KEY is required for Grok providers")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.0 if json_mode else 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                raise GrokRequestError(f"Grok API request failed with HTTP {response.status_code}")
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except GrokRequestError:
            raise
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise GrokRequestError(f"Grok API returned an invalid response: {type(exc).__name__}") from exc
        if not isinstance(content, str) or not content.strip():
            raise GrokRequestError("Grok API returned empty content")
        return content.strip()
