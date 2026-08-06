from pathlib import Path
import shutil
import uuid
from time import time

import pytest
from cryptography.fernet import Fernet

from backend.app.storage import LocalFileStorage, StorageError


def storage_root() -> Path:
    root = Path(".data") / f"test-storage-{uuid.uuid4()}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_local_storage_encrypts_uploaded_bytes() -> None:
    tmp_path = storage_root()
    key = Fernet.generate_key().decode()
    try:
        storage = LocalFileStorage(tmp_path, encryption_key=key, encryption_required=True)
        reference = storage.store(filename="report.pdf", content=b"private report", content_type="application/pdf")
        stored = next(tmp_path.iterdir())
        assert reference.startswith("local://")
        assert stored.read_bytes() != b"private report"
        assert Fernet(key.encode()).decrypt(stored.read_bytes()) == b"private report"
    finally:
        shutil.rmtree(tmp_path)


def test_production_storage_requires_encryption_key(monkeypatch) -> None:
    tmp_path = storage_root()
    monkeypatch.setenv("SMRITI_ENV", "production")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("STORAGE_ENCRYPTION_KEY", raising=False)

    from backend.app.storage import get_storage

    with pytest.raises(StorageError, match="STORAGE_ENCRYPTION_KEY"):
        get_storage()
    shutil.rmtree(tmp_path)


def test_local_storage_removes_expired_files() -> None:
    tmp_path = storage_root()
    expired = tmp_path / "expired.pdf"
    expired.write_bytes(b"old")
    import os

    os.utime(expired, (time() - 3 * 86400, time() - 3 * 86400))

    storage = LocalFileStorage(tmp_path, retention_days=2)

    assert not expired.exists()
    assert storage.cleanup_expired() == 0
    shutil.rmtree(tmp_path)
