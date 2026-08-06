"""Environment-backed application configuration."""

from dataclasses import dataclass
import os


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    db_auto_create: bool
    auth_enabled: bool
    api_token: str | None
    rate_limit_per_minute: int
    rate_limit_backend: str
    redis_url: str | None
    auth_mode: str
    oidc_issuer: str | None
    oidc_audience: str | None
    oidc_jwks_url: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("SMRITI_ENV", "development").lower()
        database_url = os.getenv("DATABASE_URL", "sqlite:///./smriti.db")
        auto_create_default = environment != "production" and database_url.startswith("sqlite")
        return cls(
            environment=environment,
            database_url=database_url,
            db_auto_create=_bool("DB_AUTO_CREATE", auto_create_default),
            auth_enabled=_bool("AUTH_ENABLED", environment == "production"),
            api_token=os.getenv("SMRITI_API_TOKEN") or None,
            rate_limit_per_minute=max(1, int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))),
            rate_limit_backend=os.getenv("RATE_LIMIT_BACKEND", "redis" if environment == "production" else "memory"),
            redis_url=os.getenv("REDIS_URL") or None,
            auth_mode=os.getenv("AUTH_MODE", "token").lower(),
            oidc_issuer=os.getenv("OIDC_ISSUER") or None,
            oidc_audience=os.getenv("OIDC_AUDIENCE") or None,
            oidc_jwks_url=os.getenv("OIDC_JWKS_URL") or None,
        )


settings = Settings.from_env()
