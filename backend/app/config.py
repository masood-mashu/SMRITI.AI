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


def validate_production_settings() -> None:
    """Fail closed when an explicitly validated production deployment is misconfigured."""
    if os.getenv("SMRITI_ENV", "development").lower() != "production":
        return
    required = {
        "AUTH_ENABLED": os.getenv("AUTH_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        "AUTH_MODE": os.getenv("AUTH_MODE", "oidc").lower() == "oidc",
        "PHI_STRICT": os.getenv("PHI_STRICT", "true").lower() in {"1", "true", "yes", "on"},
        "UPLOAD_SIGNATURE_CHECK": os.getenv("UPLOAD_SIGNATURE_CHECK", "true").lower()
        in {"1", "true", "yes", "on"},
        "RATE_LIMIT_BACKEND": os.getenv("RATE_LIMIT_BACKEND", "").lower() == "redis",
        "STORE_RAW_EXTRACTION": os.getenv("STORE_RAW_EXTRACTION", "false").lower() in {"0", "false", "no", "off"},
    }
    missing = [name for name, valid in required.items() if not valid]
    for name in ("DATABASE_URL", "REDIS_URL", "OIDC_ISSUER", "OIDC_AUDIENCE"):
        if not os.getenv(name):
            missing.append(name)
    storage_provider = os.getenv("STORAGE_PROVIDER", "").lower()
    if storage_provider == "gcs":
        for name in ("GCS_BUCKET", "GCS_KMS_KEY_NAME"):
            if not os.getenv(name):
                missing.append(name)
    elif storage_provider == "local":
        if os.getenv("STORAGE_ENCRYPTION_REQUIRED", "false").lower() not in {"1", "true", "yes", "on"}:
            missing.append("STORAGE_ENCRYPTION_REQUIRED=true")
        if not os.getenv("STORAGE_ENCRYPTION_KEY"):
            missing.append("STORAGE_ENCRYPTION_KEY")
        if int(os.getenv("STORAGE_RETENTION_DAYS", "0")) <= 0:
            missing.append("STORAGE_RETENTION_DAYS>0")
    else:
        missing.append("STORAGE_PROVIDER=gcs|local")
    if os.getenv("DB_AUTO_CREATE", "false").lower() in {"1", "true", "yes", "on"}:
        missing.append("DB_AUTO_CREATE=false")
    if missing:
        raise RuntimeError("Invalid production configuration: " + ", ".join(sorted(set(missing))))
