"""Persistence operations for the append-only health memory."""

from datetime import date
import json
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from .models import Contradiction, HealthFact, Patient, Report


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
            )
        ).first()

        if current is not None and current.fact_value == str(payload["fact_value"]):
            continue

        fact = HealthFact(
            patient_id=patient_id,
            report_id=report.report_id,
            fact_type=str(payload["fact_type"]),
            fact_key=fact_key,
            fact_value=str(payload["fact_value"]),
            unit=payload.get("unit"),
            status=str(payload.get("status", "active")),
            is_emergency_relevant=bool(payload.get("is_emergency_relevant", False)),
            effective_date=payload.get("effective_date", date.today()),
            confidence=payload.get("confidence"),
        )
        session.add(fact)
        session.flush()

        if current is not None:
            current.superseded_by = fact.fact_id
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


def get_fact_timeline(session: Session, patient_id: UUID) -> list[HealthFact]:
    return list(
        session.exec(
            select(HealthFact).where(
                HealthFact.patient_id == patient_id,
            ).order_by(HealthFact.effective_date, HealthFact.recorded_at)
        )
    )
