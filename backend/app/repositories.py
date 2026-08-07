"""Persistence operations for the append-only health memory."""

from datetime import date
import json
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import Session, select

from .models import Contradiction, HealthFact, Patient, Report, utc_now


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
            # Close the current row before inserting its replacement so the
            # unique partial index is satisfied throughout the transaction.
            current.superseded_by = fact.fact_id
            session.flush()
        session.add(fact)
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
