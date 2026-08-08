from pathlib import Path
from uuid import uuid4
import shutil

from fastapi.testclient import TestClient

from backend.app.main import app


def test_demo_mode_processes_fixture_synchronously(monkeypatch) -> None:
    storage_dir = Path(".data") / f"test-demo-{uuid4()}"
    monkeypatch.setenv("SMRITI_DEMO_MODE", "true")
    monkeypatch.setenv("SMRITI_ENV", "demo")
    monkeypatch.setenv("INGESTION_QUEUE_PROVIDER", "sync")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("PHI_STRICT", "false")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    try:
        patient_id = uuid4()
        with TestClient(app) as client:
            response = client.post(
                f"/reports?patient_id={patient_id}&fixture=true",
                files={"file": ("synthetic.txt", b"synthetic", "text/plain")},
            )
            assert response.status_code == 200
            assert response.json()["job_status"] == "succeeded"
            timeline = client.get(f"/timeline?patient_id={patient_id}")
            assert timeline.status_code == 200
            assert len(timeline.json()["facts"]) == 3
    finally:
        shutil.rmtree(storage_dir, ignore_errors=True)
