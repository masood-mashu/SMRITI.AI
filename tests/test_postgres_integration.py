"""Regression coverage that runs in CI against the real PostgreSQL service."""

from datetime import date
from uuid import uuid4

import pytest
from sqlmodel import select

from backend.app import db
from backend.app.db import session_scope
from backend.app.models import Contradiction, HealthFact
from backend.app.repositories import delete_patient_data, persist_report_and_facts


pytestmark = pytest.mark.skipif(
    db.DATABASE_URL.startswith("sqlite"),
    reason="requires PostgreSQL",
)


def test_postgres_fact_supersession_preserves_history_and_fk() -> None:
    patient_id = uuid4()
    try:
        with session_scope() as session:
            persist_report_and_facts(
                session,
                patient_id=patient_id,
                source_type="lab_result",
                raw_extraction=None,
                extracted_facts=[
                    {
                        "fact_type": "lab_value",
                        "fact_key": "HbA1c",
                        "fact_value": "7.0",
                        "effective_date": date(2026, 1, 1),
                    }
                ],
            )
        with session_scope() as session:
            persist_report_and_facts(
                session,
                patient_id=patient_id,
                source_type="lab_result",
                raw_extraction=None,
                extracted_facts=[
                    {
                        "fact_type": "lab_value",
                        "fact_key": "HbA1c",
                        "fact_value": "8.0",
                        "effective_date": date(2026, 2, 1),
                    }
                ],
            )
            facts = list(session.exec(select(HealthFact).where(HealthFact.patient_id == patient_id)))
            contradictions = list(session.exec(select(Contradiction).where(Contradiction.patient_id == patient_id)))
            assert len(facts) == 2
            assert len(contradictions) == 1
            assert sum(fact.superseded_by is None for fact in facts) == 1
    finally:
        with session_scope() as session:
            delete_patient_data(session, patient_id)
