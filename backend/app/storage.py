"""File storage boundary for uploaded reports."""

from pathlib import Path
import os
import time
from typing import Protocol
from uuid import uuid4

from cryptography.fernet import Fernet


class StorageError(RuntimeError):
    pass


class FileStorage(Protocol):
    def store(self, *, filename: str, content: bytes, content_type: str) -> str:
        """Persist bytes and return a non-sensitive reference URL."""

    def delete(self, reference: str) -> None:
        """Delete a previously stored object when processing cannot complete."""

    def read(self, reference: str) -> bytes:
        """Read a previously stored object for asynchronous processing."""


class LocalFileStorage:
    def __init__(
        self,
        root: str | Path = ".data/uploads",
        *,
        encryption_key: str | None = None,
        encryption_required: bool = False,
        retention_days: int = 0,
        cleanup_on_init: bool = True,
    ) -> None:
        self.root = Path(root)
        self._fernet = None
        if encryption_key:
            try:
                self._fernet = Fernet(encryption_key.encode())
            except (ValueError, TypeError) as exc:
                raise StorageError("STORAGE_ENCRYPTION_KEY must be a valid Fernet key") from exc
        if encryption_required and self._fernet is None:
            raise StorageError("STORAGE_ENCRYPTION_KEY is required for encrypted local storage")
        self.retention_days = max(0, retention_days)
        if cleanup_on_init:
            self.cleanup_expired()

    def store(self, *, filename: str, content: bytes, content_type: str) -> str:
        suffix = Path(filename).suffix.lower()
        key = f"{uuid4()}{suffix}"
        self.root.mkdir(parents=True, exist_ok=True)
        payload = self._fernet.encrypt(content) if self._fernet else content
        (self.root / key).write_bytes(payload)
        return f"local://{key}"

    def delete(self, reference: str) -> None:
        prefix = "local://"
        if not reference.startswith(prefix):
            raise StorageError("Invalid local storage reference")
        key = reference[len(prefix):]
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in path.parents:
            raise StorageError("Invalid local storage reference")
        if path.exists():
            path.unlink()

    def read(self, reference: str) -> bytes:
        prefix = "local://"
        if not reference.startswith(prefix):
            raise StorageError("Invalid local storage reference")
        key = reference[len(prefix):]
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in path.parents or not path.is_file():
            raise StorageError("Stored report is unavailable")
        payload = path.read_bytes()
        return self._fernet.decrypt(payload) if self._fernet else payload

    def cleanup_expired(self) -> int:
        """Remove local files older than the configured retention window."""
        if self.retention_days <= 0 or not self.root.exists():
            return 0
        cutoff = time.time() - (self.retention_days * 86400)
        removed = 0
        for path in self.root.iterdir():
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        return removed


class GcsFileStorage:
    def __init__(self, bucket_name: str, prefix: str = "reports", kms_key_name: str | None = None) -> None:
        self.bucket_name = bucket_name
        self.prefix = prefix.strip("/")
        self.kms_key_name = kms_key_name
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise StorageError("Install google-cloud-storage for STORAGE_PROVIDER=gcs") from exc
        self.client = storage.Client()

    def store(self, *, filename: str, content: bytes, content_type: str) -> str:
        suffix = Path(filename).suffix.lower()
        key = f"{self.prefix}/{uuid4()}{suffix}"
        blob = self.client.bucket(self.bucket_name).blob(key)
        blob.upload_from_string(content, content_type=content_type, kms_key_name=self.kms_key_name)
        return f"gs://{self.bucket_name}/{key}"

    def delete(self, reference: str) -> None:
        prefix = f"gs://{self.bucket_name}/"
        if not reference.startswith(prefix):
            raise StorageError("Invalid GCS storage reference")
        key = reference[len(prefix):]
        try:
            self.client.bucket(self.bucket_name).blob(key).delete()
        except Exception as exc:
            raise StorageError("Failed to delete GCS object") from exc

    def read(self, reference: str) -> bytes:
        prefix = f"gs://{self.bucket_name}/"
        if not reference.startswith(prefix):
            raise StorageError("Invalid GCS storage reference")
        key = reference[len(prefix):]
        try:
            return self.client.bucket(self.bucket_name).blob(key).download_as_bytes()
        except Exception as exc:
            raise StorageError("Stored report is unavailable") from exc


def get_storage() -> FileStorage:
    provider = os.getenv("STORAGE_PROVIDER", "local").lower()
    if provider == "local":
        production = os.getenv("SMRITI_ENV", "development").lower() == "production"
        demo_mode = os.getenv("SMRITI_DEMO_MODE", "false").lower() in {"1", "true", "yes", "on"}
        required = os.getenv("STORAGE_ENCRYPTION_REQUIRED", str(production)).lower() in {"1", "true", "yes", "on"}
        root = os.getenv("LOCAL_STORAGE_DIR") or ("/tmp/smriti-demo-uploads" if demo_mode else ".data/uploads")
        return LocalFileStorage(
            root,
            encryption_key=os.getenv("STORAGE_ENCRYPTION_KEY") or None,
            encryption_required=required,
            retention_days=int(os.getenv("STORAGE_RETENTION_DAYS", "0")),
        )
    if provider == "gcs":
        bucket = os.getenv("GCS_BUCKET")
        if not bucket:
            raise StorageError("GCS_BUCKET is required for STORAGE_PROVIDER=gcs")
        kms_key = os.getenv("GCS_KMS_KEY_NAME") or None
        if os.getenv("GCS_KMS_KEY_REQUIRED", "false").lower() in {"1", "true", "yes", "on"} and not kms_key:
            raise StorageError("GCS_KMS_KEY_NAME is required when GCS_KMS_KEY_REQUIRED=true")
        return GcsFileStorage(bucket, os.getenv("GCS_PREFIX", "reports"), kms_key_name=kms_key)
    raise StorageError(f"Unsupported STORAGE_PROVIDER: {provider}")
