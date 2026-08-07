"""Authentication, patient authorization, and rate limiting."""

from collections import defaultdict, deque
from dataclasses import dataclass
from hmac import compare_digest
import threading
import time
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings


bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    subject: str
    patient_id: str | None
    mode: str


class RateLimiter:
    """Development fallback; use Redis for multi-instance deployments."""

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


class RedisRateLimiter:
    def __init__(self, url: str) -> None:
        try:
            import redis
            self._client = redis.Redis.from_url(url, decode_responses=True)
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="Redis rate limiting is not installed") from exc

    def check(self, key: str, limit: int) -> None:
        bucket = f"smriti:rate:{key}:{int(time.time() // 60)}"
        try:
            count = self._client.incr(bucket)
            if count == 1:
                self._client.expire(bucket, 61)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Rate-limit service unavailable") from exc
        if count > limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")


rate_limiter = RateLimiter()
_redis_limiters: dict[str, RedisRateLimiter] = {}
_oidc_clients: dict[str, Any] = {}


def enforce_patient_access(request: Request, patient_id: str) -> str:
    """Validate a requested patient UUID against the authenticated identity."""
    try:
        normalized = str(UUID(patient_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid patient_id") from exc
    auth = getattr(request.state, "auth", None)
    if auth is not None and auth.mode == "oidc":
        if not auth.patient_id:
            raise HTTPException(status_code=403, detail="Token is not associated with a patient")
        if normalized != auth.patient_id:
            raise HTTPException(status_code=403, detail="Patient access denied")
    return normalized


def _oidc_context(token: str, settings: Settings) -> AuthContext:
    if not settings.oidc_issuer or not settings.oidc_audience:
        raise HTTPException(status_code=503, detail="OIDC authentication is not configured")
    jwks_url = settings.oidc_jwks_url or f"{settings.oidc_issuer.rstrip('/')}/.well-known/jwks.json"
    try:
        client = _oidc_clients.get(jwks_url)
        if client is None:
            client = jwt.PyJWKClient(jwks_url, cache_jwk_set=True)
            _oidc_clients[jwks_url] = client
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["sub", "exp", "iat"]},
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid OIDC token") from exc
    patient_id = claims.get("patient_id")
    if patient_id is not None:
        try:
            patient_id = str(UUID(str(patient_id)))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Invalid patient claim") from exc
    return AuthContext(
        subject=str(claims["sub"]),
        patient_id=patient_id,
        mode="oidc",
    )


def require_security(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    settings = Settings.from_env()
    if settings.environment == "production" and (not settings.auth_enabled or settings.auth_mode != "oidc"):
        raise HTTPException(status_code=503, detail="Production requires OIDC authentication")
    client_key = request.client.host if request.client else "unknown"
    if settings.rate_limit_backend == "redis":
        if not settings.redis_url:
            raise HTTPException(status_code=503, detail="Redis rate limiting is not configured")
        limiter = _redis_limiters.setdefault(settings.redis_url, RedisRateLimiter(settings.redis_url))
    else:
        limiter = rate_limiter
    if not settings.auth_enabled:
        request.state.auth = None
        limiter.check(f"ip:{client_key}", settings.rate_limit_per_minute)
        return
    # Keep unauthenticated and invalid-token attempts bounded by source IP.
    # Successful requests receive the stronger subject-scoped limit below.
    limiter.check(f"ip:{client_key}", min(settings.rate_limit_per_minute, 10))
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer authentication required")

    if settings.auth_mode == "oidc":
        context = _oidc_context(credentials.credentials, settings)
    else:
        if not settings.api_token:
            raise HTTPException(status_code=503, detail="Token authentication is not configured")
        if not compare_digest(credentials.credentials, settings.api_token):
            raise HTTPException(status_code=401, detail="Invalid bearer token")
        context = AuthContext(subject="static-token", patient_id=None, mode="token")
    request.state.auth = context
    limiter.check(f"subject:{context.subject}", settings.rate_limit_per_minute)
