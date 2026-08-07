from datetime import date
from uuid import uuid4

from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.models import Contradiction, HealthFact, Patient
from backend.app.repositories import (
    get_current_facts,
    get_emergency_facts,
    persist_report_and_facts,
)


def make_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def fact(value: str) -> dict:
    return {
        "fact_type": "medication",
        "fact_key": "Metformin",
        "fact_value": value,
        "effective_date": date(2026, 8, 6),
    }


def test_first_fact_is_inserted_and_current() -> None:
    patient_id = uuid4()
    with make_session() as session:
        _, facts, contradictions = persist_report_and_facts(
            session,
            patient_id=patient_id,
            source_type="prescription",
            raw_extraction={"facts": [fact("500 mg")]},
            extracted_facts=[fact("500 mg")],
        )
        session.commit()
        assert len(facts) == 1
        assert contradictions == []
        assert session.get(Patient, patient_id) is not None
        assert facts[0].superseded_by is None


def test_same_current_value_is_not_duplicated() -> None:
    patient_id = uuid4()
    with make_session() as session:
        args = {
            "patient_id": patient_id,
            "source_type": "prescription",
            "raw_extraction": None,
            "extracted_facts": [fact("500 mg")],
        }
        persist_report_and_facts(session, **args)
        _, facts, contradictions = persist_report_and_facts(session, **args)
        session.commit()
        assert facts == []
        assert contradictions == []
        assert len(session.exec(select(HealthFact)).all()) == 1


def test_same_value_with_changed_status_is_historied() -> None:
    patient_id = uuid4()
    with make_session() as session:
        persist_report_and_facts(
            session,
            patient_id=patient_id,
            source_type="prescription",
            raw_extraction=None,
            extracted_facts=[fact("500 mg")],
        )
        _, new_facts, contradictions = persist_report_and_facts(
            session,
            patient_id=patient_id,
            source_type="prescription",
            raw_extraction=None,
            extracted_facts=[{**fact("500 mg"), "status": "discontinued"}],
        )
        session.commit()
        assert len(new_facts) == 1
        assert new_facts[0].status == "discontinued"
        assert len(contradictions) == 1
        assert len(session.exec(select(HealthFact)).all()) == 2


def test_changed_value_supersedes_old_and_records_contradiction() -> None:
    patient_id = uuid4()
    with make_session() as session:
        args = {
            "patient_id": patient_id,
            "source_type": "prescription",
            "raw_extraction": None,
        }
        _, old_facts, _ = persist_report_and_facts(session, **args, extracted_facts=[fact("500 mg")])
        _, new_facts, contradictions = persist_report_and_facts(
            session, **args, extracted_facts=[fact("1000 mg")]
        )
        session.commit()
        assert old_facts[0].superseded_by == new_facts[0].fact_id
        assert len(contradictions) == 1
        contradiction = session.get(Contradiction, contradictions[0].contradiction_id)
        assert contradiction is not None
        assert contradiction.fact_id_older == old_facts[0].fact_id
        assert contradiction.fact_id_newer == new_facts[0].fact_id


def test_memory_queries_return_current_and_emergency_facts() -> None:
    patient_id = uuid4()
    allergy = {
        "fact_type": "allergy",
        "fact_key": "Penicillin",
        "fact_value": "Severe reaction",
        "is_emergency_relevant": True,
        "effective_date": date(2026, 8, 6),
    }
    condition = {
        "fact_type": "condition",
        "fact_key": "Hypertension",
        "fact_value": "Recorded",
        "is_emergency_relevant": False,
        "effective_date": date(2026, 8, 6),
    }
    with make_session() as session:
        persist_report_and_facts(
            session,
            patient_id=patient_id,
            source_type="lab_result",
            raw_extraction=None,
            extracted_facts=[allergy, condition],
        )
        session.commit()
        assert {item.fact_key for item in get_current_facts(session, patient_id)} == {
            "Penicillin",
            "Hypertension",
        }
        assert [item.fact_key for item in get_emergency_facts(session, patient_id)] == ["Penicillin"]
