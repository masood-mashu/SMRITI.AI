from uuid import uuid4

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

        timeline = client.get(f"/timeline?patient_id={patient_id}")
        assert timeline.status_code == 200
        facts = timeline.json()["facts"]
        assert {item["fact_key"] for item in facts} == {
            "Type 2 diabetes",
            "Metformin",
            "Penicillin",
        }

