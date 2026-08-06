from uuid import UUID

from fastapi import FastAPI, File, UploadFile

from .graph import smriti_graph

app = FastAPI(title="Smriti API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports")
async def upload_report(file: UploadFile = File(...), patient_id: UUID | None = None) -> dict:
    content = await file.read()
    result = smriti_graph.invoke({
        "patient_id": str(patient_id) if patient_id else "demo-patient",
        "filename": file.filename or "upload",
        "content_type": file.content_type or "application/octet-stream",
        "report_bytes": content,
    })
    result.pop("report_bytes", None)
    return {"status": "accepted", "filename": file.filename, "graph": result}
