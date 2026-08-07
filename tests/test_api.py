from uuid import uuid4
from datetime import date
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import select

from backend.app.db import session_scope
from backend.app.main import app
from backend.app.models import Contradiction
from backend.app.repositories import persist_report_and_facts
from backend.app.security import rate_limiter


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


def test_timeline_is_paginated() -> None:
    patient_id = uuid4()
    with TestClient(app) as client:
        upload = client.post(
            f"/reports?patient_id={patient_id}&fixture=true",
            files={"file": ("fixture.pdf", b"synthetic", "application/pdf")},
        )
        assert upload.status_code == 200
        response = client.get(f"/timeline?patient_id={patient_id}&limit=1")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["facts"]) == 1
        assert payload["pagination"] == {"offset": 0, "limit": 1, "total": 3, "has_more": True}


def test_upload_persists_scrubbed_text_only(monkeypatch) -> None:
    storage_dir = Path(".data") / f"test-scrubbed-upload-{uuid4()}"
    monkeypatch.setenv("SMRITI_ENV", "development")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("PII_PROVIDER", "regex")
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/reports?patient_id={uuid4()}&fixture=true",
                files={"file": ("note.txt", b"Contact patient@example.com", "text/plain")},
            )
            assert response.status_code == 200
            stored = next(storage_dir.iterdir()).read_bytes()
            assert b"patient@example.com" not in stored
            assert b"[REDACTED]" in stored
    finally:
        shutil.rmtree(storage_dir, ignore_errors=True)


def test_request_body_limit_is_enforced(monkeypatch) -> None:
    monkeypatch.setenv("MAX_REQUEST_BYTES", "2")
    with TestClient(app) as client:
        response = client.post("/health", content=b"123")
        assert response.status_code == 413


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


def test_contradiction_review_records_decision_without_mutating_facts() -> None:
    rate_limiter._events.clear()
    patient_id = uuid4()
    fact = {
        "fact_type": "medication",
        "fact_key": "Medication dose",
        "fact_value": "5 mg",
        "effective_date": date(2026, 1, 1),
    }
    changed = {**fact, "fact_value": "10 mg"}
    with session_scope() as session:
        persist_report_and_facts(
            session,
            patient_id=patient_id,
            source_type="prescription",
            raw_extraction={"facts": [fact]},
            extracted_facts=[fact],
        )
        persist_report_and_facts(
            session,
            patient_id=patient_id,
            source_type="prescription",
            raw_extraction={"facts": [changed]},
            extracted_facts=[changed],
        )
        contradiction_id = session.exec(
            select(Contradiction.contradiction_id).where(Contradiction.patient_id == patient_id)
        ).one()

    with TestClient(app) as client:
        response = client.post(
            f"/contradictions/{contradiction_id}/review?patient_id={patient_id}",
            json={"decision": "confirm_newer", "reviewer_note": "Reviewed source prescription."},
        )
        assert response.status_code == 200
        assert response.json()["resolved"] is True
        timeline = client.get(f"/timeline?patient_id={patient_id}").json()
        assert len(timeline["facts"]) == 2
        assert timeline["contradictions"] == []
