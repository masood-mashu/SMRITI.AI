"""Run the configured local-storage retention cleanup.

Schedule this command with Cloud Scheduler/Cloud Run Jobs or an equivalent
platform scheduler when local encrypted storage is used. GCS retention should
be enforced with a bucket lifecycle policy instead.
"""

from __future__ import annotations

import sys
import os

from backend.app.storage import LocalFileStorage, StorageError


def main() -> int:
    try:
        storage = LocalFileStorage(
            root=os.getenv("LOCAL_STORAGE_DIR", ".data/uploads"),
            retention_days=int(os.getenv("STORAGE_RETENTION_DAYS", "0")),
            encryption_key=os.getenv("STORAGE_ENCRYPTION_KEY") or None,
            encryption_required=False,
            cleanup_on_init=False,
        )
        removed = storage.cleanup_expired()
    except StorageError as exc:
        print(f"Storage cleanup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Local storage cleanup removed {removed} expired file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
