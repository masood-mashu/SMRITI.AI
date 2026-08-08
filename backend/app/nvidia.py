"""NVIDIA NIM OpenAI-compatible REST client."""

from __future__ import annotations

import os
from typing import Any

import requests


class NvidiaRequestError(RuntimeError):
    """Raised when the NVIDIA hosted endpoint cannot return a response."""


class NvidiaClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        session: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.base_url = (base_url or os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")).rstrip("/")
        self.model = model or os.getenv("NVIDIA_MODEL", "openai/gpt-oss-20b")
        self.timeout = timeout or float(os.getenv("API_TIMEOUT_SECONDS", "60"))
        self.session = session or requests

    def complete(self, *, messages: list[dict[str, str]], json_mode: bool = False) -> str:
        if not self.api_key:
            raise NvidiaRequestError("NVIDIA_API_KEY is required for NVIDIA providers")
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
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                raise NvidiaRequestError(f"NVIDIA API request failed with HTTP {response.status_code}")
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except NvidiaRequestError:
            raise
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise NvidiaRequestError(f"NVIDIA API returned an invalid response: {type(exc).__name__}") from exc
        if not isinstance(content, str) or not content.strip():
            raise NvidiaRequestError("NVIDIA API returned empty content")
        return content.strip()
