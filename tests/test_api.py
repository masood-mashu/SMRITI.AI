from uuid import uuid4
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


def test_fixture_upload_populates_timeline() -> None:
    patient_id = uuid4()
    with TestClient(app) as client:
        upload = client.post(
            f"/reports?patient_id={patient_id}&fixture=true",
            files={"file": ("fixture.pdf", b"synthetic", "application/pdf")},
        )
        assert upload.status_code == 200
        assert upload.json()["graph"]["memory_updated"] is True
        assert len(upload.json()["graph"]["persisted_fact_ids"]) == 3
        assert upload.json()["graph"]["file_url"].startswith("local://")

        timeline = client.get(f"/timeline?patient_id={patient_id}")
        assert timeline.status_code == 200
        facts = timeline.json()["facts"]
        assert {item["fact_key"] for item in facts} == {
            "Type 2 diabetes",
            "Metformin",
            "Penicillin",
        }
        assert timeline.json()["contradictions"] == []


def test_empty_upload_is_rejected() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/reports",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400


def test_unconfigured_real_extraction_fails_explicitly(monkeypatch) -> None:
    monkeypatch.delenv("EXTRACTION_PROVIDER", raising=False)
    monkeypatch.setenv("SMRITI_ENV", "development")
    storage_dir = Path(".data") / f"test-api-upload-{uuid4()}"
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(storage_dir))
    try:
        with TestClient(app) as client:
            response = client.post(
                "/reports",
                files={"file": ("report.txt", b"medical report", "text/plain")},
            )
            assert response.status_code == 503
            assert "extraction is not configured" in response.json()["detail"]
            assert list(storage_dir.iterdir()) == []
    finally:
        shutil.rmtree(storage_dir, ignore_errors=True)


def test_fixture_upload_is_rejected_in_production(monkeypatch) -> None:
    monkeypatch.setenv("SMRITI_ENV", "production")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    with TestClient(app) as client:
        response = client.post(
            "/reports?fixture=true",
            files={"file": ("fixture.txt", b"synthetic", "text/plain")},
        )
        assert response.status_code == 400
        assert response.headers["X-Request-ID"]


def test_production_upload_checks_file_signature(monkeypatch) -> None:
    monkeypatch.setenv("SMRITI_ENV", "production")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    with TestClient(app) as client:
        response = client.post(
            "/reports",
            files={"file": ("report.pdf", b"not a pdf", "application/pdf")},
        )
        assert response.status_code == 415


def test_translation_rejects_unsupported_language() -> None:
    with TestClient(app) as client:
        response = client.post("/translate?language=fr")
        assert response.status_code == 422
        assert "Unsupported language" in response.json()["detail"]
