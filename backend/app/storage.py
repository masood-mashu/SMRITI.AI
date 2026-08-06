"""File storage boundary for uploaded reports."""

from pathlib import Path
import os
from typing import Protocol
from uuid import uuid4


class StorageError(RuntimeError):
    pass


class FileStorage(Protocol):
    def store(self, *, filename: str, content: bytes, content_type: str) -> str:
        """Persist bytes and return a non-sensitive reference URL."""


class LocalFileStorage:
    def __init__(self, root: str | Path = ".data/uploads") -> None:
        self.root = Path(root)

    def store(self, *, filename: str, content: bytes, content_type: str) -> str:
        suffix = Path(filename).suffix.lower()
        key = f"{uuid4()}{suffix}"
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / key).write_bytes(content)
        return f"local://{key}"


class GcsFileStorage:
    def __init__(self, bucket_name: str, prefix: str = "reports") -> None:
        self.bucket_name = bucket_name
        self.prefix = prefix.strip("/")
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise StorageError("Install google-cloud-storage for STORAGE_PROVIDER=gcs") from exc
        self.client = storage.Client()

    def store(self, *, filename: str, content: bytes, content_type: str) -> str:
        suffix = Path(filename).suffix.lower()
        key = f"{self.prefix}/{uuid4()}{suffix}"
        blob = self.client.bucket(self.bucket_name).blob(key)
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{self.bucket_name}/{key}"


def get_storage() -> FileStorage:
    provider = os.getenv("STORAGE_PROVIDER", "local").lower()
    if provider == "local":
        return LocalFileStorage(os.getenv("LOCAL_STORAGE_DIR", ".data/uploads"))
    if provider == "gcs":
        bucket = os.getenv("GCS_BUCKET")
        if not bucket:
            raise StorageError("GCS_BUCKET is required for STORAGE_PROVIDER=gcs")
        return GcsFileStorage(bucket, os.getenv("GCS_PREFIX", "reports"))
    raise StorageError(f"Unsupported STORAGE_PROVIDER: {provider}")
