from uuid import UUID

from fastapi import FastAPI, File, UploadFile

from .graph import (
    doctor_brief_graph,
    emergency_graph,
    language_graph,
    smriti_ingestion_graph,
)

app = FastAPI(title="Smriti API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports")
async def upload_report(file: UploadFile = File(...), patient_id: UUID | None = None) -> dict:
    content = await file.read()
    result = smriti_ingestion_graph.invoke({
        "patient_id": str(patient_id) if patient_id else "demo-patient",
        "filename": file.filename or "upload",
        "content_type": file.content_type or "application/octet-stream",
        "report_bytes": content,
    })
    result.pop("report_bytes", None)
    return {"status": "accepted", "filename": file.filename, "graph": result}


@app.post("/brief")
def generate_doctor_brief(patient_id: UUID | None = None) -> dict:
    result = doctor_brief_graph.invoke({"patient_id": str(patient_id) if patient_id else "demo-patient"})
    return {"status": "generated", "graph": result}


@app.post("/emergency")
def generate_emergency_card(patient_id: UUID | None = None) -> dict:
    result = emergency_graph.invoke({"patient_id": str(patient_id) if patient_id else "demo-patient"})
    return {"status": "generated", "graph": result}


@app.post("/translate")
def translate_output(patient_id: UUID | None = None, language: str = "en") -> dict:
    result = language_graph.invoke({
        "patient_id": str(patient_id) if patient_id else "demo-patient",
        "target_language": language,
    })
    return {"status": "generated", "language": language, "graph": result}
