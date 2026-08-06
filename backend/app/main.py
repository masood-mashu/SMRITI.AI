from contextlib import asynccontextmanager
from uuid import UUID
from pathlib import Path
from typing import Literal
import os
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .db import check_database, init_db, session_scope
from .extractor import ExtractionError, ProviderConfigurationError
from .generation import GenerationError
from .graph import (
    doctor_brief_graph,
    emergency_graph,
    language_graph,
    smriti_ingestion_graph,
)
from .repositories import get_fact_timeline, get_patient_contradictions
from .models import HealthFact
from .storage import StorageError, get_storage
from .observability import audit_log, trace_span
from .security import enforce_patient_access, require_security
from .mcp_server import router as mcp_router

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Smriti API", version="0.1.0", lifespan=lifespan)
app.include_router(mcp_router)
DEFAULT_PATIENT_ID = UUID("00000000-0000-0000-0000-000000000001")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "text/plain"}
ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}


@app.exception_handler(GenerationError)
async def generation_error_handler(request: Request, exc: GenerationError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = str(uuid4())
    started = time.perf_counter()
    response = None
    status_code = 500
    try:
        with trace_span("http.request", method=request.method, path=request.url.path):
            response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        audit_log(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )


def resolve_patient_id(patient_id: UUID | None, request: Request | None = None) -> str:
    auth = getattr(request.state, "auth", None) if request is not None else None
    if auth is not None and auth.mode == "oidc":
        if not auth.patient_id:
            raise HTTPException(status_code=403, detail="Token is not associated with a patient")
        if patient_id is not None and str(patient_id) != auth.patient_id:
            raise HTTPException(status_code=403, detail="Patient access denied")
        return auth.patient_id
    if patient_id is not None:
        return enforce_patient_access(request, str(patient_id)) if request is not None else str(patient_id)
    if os.getenv("SMRITI_ENV", "development").lower() not in {"development", "test"}:
        raise HTTPException(status_code=400, detail="patient_id is required")
    return str(DEFAULT_PATIENT_ID)


def validate_upload(*, filename: str, content_type: str, content: bytes) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded report is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded report exceeds the 10 MB limit")
    suffix = Path(filename).suffix.lower()
    expected_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".txt": "text/plain",
    }
    if suffix not in ALLOWED_SUFFIXES or content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported report type")
    if expected_types[suffix] != content_type:
        raise HTTPException(status_code=415, detail="Unsupported report type")


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    try:
        check_database()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready"}


@app.post("/reports", dependencies=[Depends(require_security)])
async def upload_report(
    request: Request,
    file: UploadFile = File(...),
    patient_id: UUID | None = None,
    source_type: Literal["lab_result", "discharge_summary", "prescription", "other"] = "other",
    fixture: bool = False,
) -> dict:
    content = await file.read()
    validate_upload(
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        content=content,
    )
    try:
        file_url = get_storage().store(
            filename=file.filename or "upload",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        result = smriti_ingestion_graph.invoke({
            "patient_id": resolve_patient_id(patient_id, request),
            "filename": file.filename or "upload",
            "content_type": file.content_type or "application/octet-stream",
            "source_type": source_type,
            "use_fixture": fixture,
            "file_url": file_url,
            "report_bytes": content,
        })
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result.pop("report_bytes", None)
    return {"status": "accepted", "filename": file.filename, "graph": result}


@app.get("/timeline", dependencies=[Depends(require_security)])
def get_timeline(request: Request, patient_id: UUID | None = None) -> dict:
    resolved_id = UUID(resolve_patient_id(patient_id, request))
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


@app.post("/brief", dependencies=[Depends(require_security)])
def generate_doctor_brief(request: Request, patient_id: UUID | None = None) -> dict:
    result = doctor_brief_graph.invoke({"patient_id": resolve_patient_id(patient_id, request)})
    return {"status": "generated", "graph": result}


@app.post("/emergency", dependencies=[Depends(require_security)])
def generate_emergency_card(request: Request, patient_id: UUID | None = None) -> dict:
    result = emergency_graph.invoke({"patient_id": resolve_patient_id(patient_id, request)})
    return {"status": "generated", "graph": result}


@app.post("/translate", dependencies=[Depends(require_security)])
def translate_output(request: Request, patient_id: UUID | None = None, language: str = "en") -> dict:
    result = language_graph.invoke({
        "patient_id": resolve_patient_id(patient_id, request),
        "target_language": language,
    })
    return {"status": "generated", "language": language, "graph": result}
