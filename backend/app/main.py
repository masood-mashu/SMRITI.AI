from uuid import UUID

from fastapi import FastAPI, File, UploadFile

from .db import init_db
from .graph import (
    doctor_brief_graph,
    emergency_graph,
    language_graph,
    smriti_ingestion_graph,
)

app = FastAPI(title="Smriti API", version="0.1.0")
DEFAULT_PATIENT_ID = UUID("00000000-0000-0000-0000-000000000001")


def resolve_patient_id(patient_id: UUID | None) -> str:
    return str(patient_id or DEFAULT_PATIENT_ID)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports")
async def upload_report(file: UploadFile = File(...), patient_id: UUID | None = None) -> dict:
    content = await file.read()
    result = smriti_ingestion_graph.invoke({
            "patient_id": resolve_patient_id(patient_id),
        "filename": file.filename or "upload",
        "content_type": file.content_type or "application/octet-stream",
        "source_type": "other",
        "report_bytes": content,
    })
    result.pop("report_bytes", None)
    return {"status": "accepted", "filename": file.filename, "graph": result}


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
