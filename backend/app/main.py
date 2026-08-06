from uuid import UUID

from fastapi import FastAPI, File, HTTPException, UploadFile

from .db import init_db, session_scope
from .extractor import ExtractionError, ProviderConfigurationError
from .graph import (
    doctor_brief_graph,
    emergency_graph,
    language_graph,
    smriti_ingestion_graph,
)
from .repositories import get_fact_timeline, get_patient_contradictions
from .models import HealthFact

app = FastAPI(title="Smriti API", version="0.1.0")
DEFAULT_PATIENT_ID = UUID("00000000-0000-0000-0000-000000000001")


def resolve_patient_id(patient_id: UUID | None) -> str:
    return str(patient_id or DEFAULT_PATIENT_ID)


def serialize_fact(fact: HealthFact) -> dict:
    return {
        "fact_id": str(fact.fact_id),
        "patient_id": str(fact.patient_id),
        "report_id": str(fact.report_id) if fact.report_id else None,
        "fact_type": fact.fact_type,
        "fact_key": fact.fact_key,
        "fact_value": fact.fact_value,
        "unit": fact.unit,
        "status": fact.status,
        "is_emergency_relevant": fact.is_emergency_relevant,
        "effective_date": fact.effective_date.isoformat(),
        "recorded_at": fact.recorded_at.isoformat(),
        "superseded_by": str(fact.superseded_by) if fact.superseded_by else None,
        "confidence": fact.confidence,
    }


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports")
async def upload_report(
    file: UploadFile = File(...),
    patient_id: UUID | None = None,
    source_type: str = "other",
    fixture: bool = False,
) -> dict:
    content = await file.read()
    try:
        result = smriti_ingestion_graph.invoke({
            "patient_id": resolve_patient_id(patient_id),
            "filename": file.filename or "upload",
            "content_type": file.content_type or "application/octet-stream",
            "source_type": source_type,
            "use_fixture": fixture,
            "report_bytes": content,
        })
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result.pop("report_bytes", None)
    return {"status": "accepted", "filename": file.filename, "graph": result}


@app.get("/timeline")
def get_timeline(patient_id: UUID | None = None) -> dict:
    resolved_id = UUID(resolve_patient_id(patient_id))
    with session_scope() as session:
        facts = get_fact_timeline(session, resolved_id)
        contradictions = get_patient_contradictions(session, resolved_id)
    return {
        "patient_id": str(resolved_id),
        "facts": [serialize_fact(fact) for fact in facts],
        "contradictions": [
            {
                "contradiction_id": str(item.contradiction_id),
                "fact_id_older": str(item.fact_id_older),
                "fact_id_newer": str(item.fact_id_newer),
                "description": item.description,
                "detected_at": item.detected_at.isoformat(),
                "resolved": item.resolved,
            }
            for item in contradictions
        ],
    }


@app.post("/brief")
def generate_doctor_brief(patient_id: UUID | None = None) -> dict:
    result = doctor_brief_graph.invoke({"patient_id": resolve_patient_id(patient_id)})
    return {"status": "generated", "graph": result}


@app.post("/emergency")
def generate_emergency_card(patient_id: UUID | None = None) -> dict:
    result = emergency_graph.invoke({"patient_id": resolve_patient_id(patient_id)})
    return {"status": "generated", "graph": result}


@app.post("/translate")
def translate_output(patient_id: UUID | None = None, language: str = "en") -> dict:
    result = language_graph.invoke({
        "patient_id": resolve_patient_id(patient_id),
        "target_language": language,
    })
    return {"status": "generated", "language": language, "graph": result}
