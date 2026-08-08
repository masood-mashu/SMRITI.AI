"""Persistence operations for the append-only health memory."""

from datetime import date
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlmodel import Session, select

from .models import Contradiction, HealthFact, IngestionJob, Patient, Report, utc_now


def json_safe(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def ensure_patient(session: Session, patient_id: UUID, display_name: str = "Smriti patient") -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        patient = Patient(patient_id=patient_id, display_name=display_name)
        session.add(patient)
        session.flush()
    return patient


def create_ingestion_job(
    session: Session,
    *,
    patient_id: UUID,
    source_type: str,
    file_url: str | None,
    filename: str = "report",
    content_type: str = "application/octet-stream",
    use_fixture: bool = False,
    pii_redactions: int = 0,
    pii_provider: str = "unknown",
) -> IngestionJob:
    ensure_patient(session, patient_id)
    job = IngestionJob(
        patient_id=patient_id,
        source_type=source_type,
        file_url=file_url,
        filename=filename,
        content_type=content_type,
        use_fixture=use_fixture,
        pii_redactions=pii_redactions,
        pii_provider=pii_provider,
        status="pending",
    )
    session.add(job)
    session.flush()
    return job


def update_ingestion_job(
    session: Session,
    job_id: UUID,
    *,
    status: str,
    report_id: UUID | None = None,
    error: str | None = None,
) -> IngestionJob | None:
    job = session.get(IngestionJob, job_id)
    if job is None:
        return None
    job.status = status
    job.report_id = report_id
    job.error = error
    job.updated_at = utc_now()
    session.add(job)
    session.flush()
    return job


def get_ingestion_job(session: Session, *, job_id: UUID, patient_id: UUID) -> IngestionJob | None:
    job = session.get(IngestionJob, job_id)
    if job is None or job.patient_id != patient_id:
        return None
    return job


def persist_report_and_facts(
    session: Session,
    *,
    patient_id: UUID,
    source_type: str,
    raw_extraction: dict[str, Any] | None,
    extracted_facts: list[dict[str, Any]],
    file_url: str | None = None,
    display_name: str = "Smriti patient",
) -> tuple[Report, list[HealthFact], list[Contradiction]]:
    """Insert a report and merge extracted facts without overwriting history."""
    ensure_patient(session, patient_id, display_name)
    report = Report(
        patient_id=patient_id,
        source_type=source_type,
        file_url=file_url,
        raw_extraction=json_safe(raw_extraction),
    )
    session.add(report)
    session.flush()

    inserted: list[HealthFact] = []
    contradictions: list[Contradiction] = []
    for payload in extracted_facts:
        fact_key = str(payload["fact_key"])
        current = session.exec(
            select(HealthFact).where(
                HealthFact.patient_id == patient_id,
                HealthFact.fact_key == fact_key,
                HealthFact.superseded_by.is_(None),
            ).with_for_update()
        ).first()

        payload_value = str(payload["fact_value"])
        payload_unit = payload.get("unit")
        payload_status = str(payload.get("status", "active"))
        payload_emergency = bool(payload.get("is_emergency_relevant", False))
        payload_date = payload.get("effective_date", date.today())
        payload_confidence = payload.get("confidence")

        if current is not None and (
            current.fact_value == payload_value
            and current.unit == payload_unit
            and current.status == payload_status
            and current.is_emergency_relevant == payload_emergency
            and current.effective_date == payload_date
            and current.confidence == payload_confidence
        ):
            continue

        fact = HealthFact(
            fact_id=uuid4(),
            patient_id=patient_id,
            report_id=report.report_id,
            fact_type=str(payload["fact_type"]),
            fact_key=fact_key,
            fact_value=payload_value,
            unit=payload_unit,
            status=payload_status,
            is_emergency_relevant=payload_emergency,
            effective_date=payload_date,
            confidence=payload_confidence,
        )
        if current is not None:
            # The partial unique index requires the old row to stop being
            # current before inserting its replacement, while the
            # self-referential FK requires the replacement to exist before the
            # final link is written. A temporary self-link satisfies both
            # immediate constraints; the transaction is atomic, so callers
            # never observe this intermediate state.
            current.superseded_by = current.fact_id
            session.flush()
            session.add(fact)
            session.flush()
        else:
            session.add(fact)
            session.flush()
        if current is not None:
            current.superseded_by = fact.fact_id
            session.flush()

        if current is not None:
            contradiction = Contradiction(
                patient_id=patient_id,
                fact_id_older=current.fact_id,
                fact_id_newer=fact.fact_id,
                description=(
                    f"{fact_key} changed from '{current.fact_value}' "
                    f"to '{fact.fact_value}'."
                ),
            )
            session.add(contradiction)
            contradictions.append(contradiction)

        inserted.append(fact)

    session.flush()
    return report, inserted, contradictions


def get_current_facts(session: Session, patient_id: UUID) -> list[HealthFact]:
    return list(
        session.exec(
            select(HealthFact).where(
                HealthFact.patient_id == patient_id,
                HealthFact.superseded_by.is_(None),
            ).order_by(HealthFact.effective_date)
        )
    )


def get_emergency_facts(session: Session, patient_id: UUID) -> list[HealthFact]:
    return list(
        session.exec(
            select(HealthFact).where(
                HealthFact.patient_id == patient_id,
                HealthFact.superseded_by.is_(None),
                HealthFact.is_emergency_relevant.is_(True),
            ).order_by(HealthFact.effective_date)
        )
    )


def get_patient_contradictions(session: Session, patient_id: UUID) -> list[Contradiction]:
    return list(
        session.exec(
            select(Contradiction).where(
                Contradiction.patient_id == patient_id,
                Contradiction.resolved.is_(False),
            ).order_by(Contradiction.detected_at)
        )
    )


def delete_patient_data(session: Session, patient_id: UUID) -> list[str] | None:
    """Delete a patient's database records and return report storage references."""
    patient = session.get(Patient, patient_id)
    if patient is None:
        return None

    reports = list(session.exec(select(Report).where(Report.patient_id == patient_id)))
    jobs = list(session.exec(select(IngestionJob).where(IngestionJob.patient_id == patient_id)))
    facts = list(session.exec(select(HealthFact).where(HealthFact.patient_id == patient_id)))
    contradictions = list(session.exec(select(Contradiction).where(Contradiction.patient_id == patient_id)))

    # Break self-referential fact links before deleting the fact rows. Use a
    # temporary self-link rather than NULL: multiple historical rows share a
    # fact_key, so clearing all links would violate the partial unique index.
    for fact in facts:
        fact.superseded_by = fact.fact_id
        session.add(fact)
    session.flush()
    for contradiction in contradictions:
        session.delete(contradiction)
    for fact in facts:
        session.delete(fact)
    for job in jobs:
        session.delete(job)
    for report in reports:
        session.delete(report)
    # Flush child deletions before removing the patient. PostgreSQL enforces
    # these foreign keys immediately and does not infer this order from the
    # SQLModel classes because explicit relationships are not declared.
    session.flush()
    session.delete(patient)
    session.flush()
    return [report.file_url for report in reports if report.file_url]


def review_contradiction(
    session: Session,
    *,
    contradiction_id: UUID,
    patient_id: UUID,
    decision: str,
    reviewer: str,
    reviewer_note: str | None = None,
) -> Contradiction | None:
    """Record a human review without changing either historical fact."""
    contradiction = session.get(Contradiction, contradiction_id)
    if contradiction is None or contradiction.patient_id != patient_id:
        return None
    contradiction.review_decision = decision
    contradiction.reviewer_note = reviewer_note
    contradiction.reviewed_at = utc_now()
    contradiction.reviewed_by = reviewer
    contradiction.resolved = decision != "leave_unresolved"
    session.add(contradiction)
    session.flush()
    return contradiction


def get_fact_timeline(session: Session, patient_id: UUID) -> list[HealthFact]:
    return list(
        session.exec(
            select(HealthFact).where(
                HealthFact.patient_id == patient_id,
            ).order_by(HealthFact.effective_date, HealthFact.recorded_at)
        )
    )


def get_fact_timeline_page(
    session: Session, patient_id: UUID, *, offset: int = 0, limit: int = 100
) -> tuple[list[HealthFact], int]:
    """Return a bounded timeline page and its total size."""
    total = session.exec(
        select(func.count()).select_from(HealthFact).where(HealthFact.patient_id == patient_id)
    ).one()
    facts = list(
        session.exec(
            select(HealthFact)
            .where(HealthFact.patient_id == patient_id)
            .order_by(HealthFact.effective_date, HealthFact.recorded_at)
            .offset(offset)
            .limit(limit)
        )
    )
    return facts, int(total)
