"""Opt-in API security and per-process rate limiting."""

from collections import defaultdict, deque
from hmac import compare_digest
import os
import threading
import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer = HTTPBearer(auto_error=False)


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= 60:
                events.popleft()
            if len(events) >= limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            events.append(now)


rate_limiter = RateLimiter()


def require_security(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    client_key = request.client.host if request.client else "unknown"
    limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    rate_limiter.check(client_key, limit)

    if os.getenv("AUTH_ENABLED", "false").lower() != "true":
        return

    expected = os.getenv("SMRITI_API_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Authentication is enabled but not configured")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer authentication required")
    if not compare_digest(credentials.credentials, expected):
        raise HTTPException(status_code=401, detail="Invalid bearer token")

