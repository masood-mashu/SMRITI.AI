from contextlib import asynccontextmanager
from uuid import UUID
from pathlib import Path
from typing import Literal
import os
import time
import json
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from .db import check_database, init_db, session_scope
from .config import validate_production_settings
from .extractor import ExtractionError, ProviderConfigurationError
from .generation import GenerationError
from .graph import (
    doctor_brief_graph,
    emergency_graph,
    language_graph,
    smriti_ingestion_graph,
    stream_doctor_brief,
    stream_emergency,
    stream_language,
)
from .repositories import get_fact_timeline_page, get_patient_contradictions, review_contradiction
from .models import HealthFact
from .storage import StorageError, get_storage
from .observability import audit_log, prometheus_metrics, record_metric, trace_span
from .security import enforce_patient_access, require_security
from .mcp_server import router as mcp_router
from .privacy import PrivacyPolicyError, get_pii_scrubber

@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("SMRITI_VALIDATE_PRODUCTION", "false").lower() in {"1", "true", "yes", "on"}:
        validate_production_settings()
    init_db()
    yield


app = FastAPI(title="Smriti API", version="0.1.0", lifespan=lifespan)
app.include_router(mcp_router)
DEFAULT_PATIENT_ID = UUID("00000000-0000-0000-0000-000000000001")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "text/plain"}
ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}
SUPPORTED_LANGUAGES = {"en", "hi", "kn"}


class ContradictionReviewRequest(BaseModel):
    decision: Literal["confirm_older", "confirm_newer", "leave_unresolved"]
    reviewer_note: str | None = Field(default=None, max_length=2000)


@app.exception_handler(GenerationError)
async def generation_error_handler(request: Request, exc: GenerationError) -> JSONResponse:
    response = JSONResponse(status_code=502, content={"detail": str(exc)})
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = None
    status_code = 500
    try:
        declared_length = request.headers.get("content-length")
        max_request_bytes = int(os.getenv("MAX_REQUEST_BYTES", str(MAX_UPLOAD_BYTES + 2 * 1024 * 1024)))
        if declared_length and int(declared_length) > max_request_bytes:
            response = JSONResponse(status_code=413, content={"detail": "Request body is too large"})
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            return response
        with trace_span("http.request", method=request.method, path=request.url.path):
            response = await call_next(request)
        status_code = response.status_code
        record_metric("http_requests", method=request.method, path=request.url.path, status=str(status_code))
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if os.getenv("SMRITI_ENV", "development").lower() == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
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
    strict_signature = os.getenv(
        "UPLOAD_SIGNATURE_CHECK",
        "true" if os.getenv("SMRITI_ENV", "development").lower() == "production" else "false",
    ).lower() in {"1", "true", "yes", "on"}
    if not strict_signature:
        return
    signatures = {
        ".pdf": content.startswith(b"%PDF-"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".txt": True,
    }
    if not signatures[suffix]:
        raise HTTPException(status_code=415, detail="File signature does not match the declared type")


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


@app.get("/metrics", dependencies=[Depends(require_security)])
def metrics() -> PlainTextResponse:
    return PlainTextResponse(prometheus_metrics(), media_type="text/plain; version=0.0.4")


@app.post("/reports", dependencies=[Depends(require_security)])
async def upload_report(
    request: Request,
    file: UploadFile = File(...),
    patient_id: UUID | None = None,
    source_type: Literal["lab_result", "discharge_summary", "prescription", "other"] = "other",
    fixture: bool = False,
) -> dict:
    environment = os.getenv("SMRITI_ENV", "development").lower()
    if fixture and environment not in {"development", "test"}:
        raise HTTPException(status_code=400, detail="fixture mode is available only in development and test environments")
    content = await file.read()
    validate_upload(
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        content=content,
    )
    resolved_patient_id = resolve_patient_id(patient_id, request)
    try:
        # Sanitize before persistence so raw uploaded PHI is never stored by the
        # storage provider. Binary files are rejected in strict production mode.
        scrubbed = get_pii_scrubber().scrub(
            content=content,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
        )
    except PrivacyPolicyError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    content = scrubbed.content
    try:
        storage = get_storage()
        file_url = storage.store(
            filename=file.filename or "upload",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        result = smriti_ingestion_graph.invoke({
            "patient_id": resolved_patient_id,
            "filename": file.filename or "upload",
            "content_type": file.content_type or "application/octet-stream",
            "source_type": source_type,
            "use_fixture": fixture,
            "file_url": file_url,
            "report_bytes": content,
            "report_is_scrubbed": True,
            "pii_redactions": scrubbed.redactions,
            "pii_provider": scrubbed.provider,
        })
    except ProviderConfigurationError as exc:
        try:
            storage.delete(file_url)
        except StorageError:
            pass
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExtractionError as exc:
        try:
            storage.delete(file_url)
        except StorageError:
            pass
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result.pop("report_bytes", None)
    return {"status": "accepted", "filename": file.filename, "graph": result}


@app.get("/timeline", dependencies=[Depends(require_security)])
def get_timeline(
    request: Request,
    patient_id: UUID | None = None,
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    resolved_id = UUID(resolve_patient_id(patient_id, request))
    with session_scope() as session:
        facts, total_facts = get_fact_timeline_page(session, resolved_id, offset=offset, limit=limit)
        contradictions = get_patient_contradictions(session, resolved_id)
    return {
        "patient_id": str(resolved_id),
        "facts": [serialize_fact(fact) for fact in facts],
        "pagination": {"offset": offset, "limit": limit, "total": total_facts, "has_more": offset + len(facts) < total_facts},
        "contradictions": [
            {
                "contradiction_id": str(item.contradiction_id),
                "fact_id_older": str(item.fact_id_older),
                "fact_id_newer": str(item.fact_id_newer),
                "description": item.description,
                "detected_at": item.detected_at.isoformat(),
                "resolved": item.resolved,
                "review_decision": item.review_decision,
                "reviewer_note": item.reviewer_note,
                "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
                "reviewed_by": item.reviewed_by,
            }
            for item in contradictions
        ],
    }


@app.post("/brief", dependencies=[Depends(require_security)])
def generate_doctor_brief(request: Request, patient_id: UUID | None = None) -> dict:
    result = doctor_brief_graph.invoke({"patient_id": resolve_patient_id(patient_id, request)})
    return {"status": "generated", "graph": result}


@app.post("/contradictions/{contradiction_id}/review", dependencies=[Depends(require_security)])
def review_contradiction_endpoint(
    contradiction_id: UUID,
    review: ContradictionReviewRequest,
    request: Request,
    patient_id: UUID | None = None,
) -> dict:
    resolved_patient_id = UUID(resolve_patient_id(patient_id, request))
    auth = getattr(request.state, "auth", None)
    reviewer = auth.subject if auth is not None else "development"
    with session_scope() as session:
        contradiction = review_contradiction(
            session,
            contradiction_id=contradiction_id,
            patient_id=resolved_patient_id,
            decision=review.decision,
            reviewer=reviewer,
            reviewer_note=review.reviewer_note,
        )
        if contradiction is None:
            raise HTTPException(status_code=404, detail="Contradiction not found")
    audit_log(
        "contradiction_reviewed",
        contradiction_id=str(contradiction_id),
        patient_id=str(resolved_patient_id),
        decision=review.decision,
        reviewer=reviewer,
    )
    return {
        "status": "reviewed",
        "contradiction_id": str(contradiction.contradiction_id),
        "patient_id": str(contradiction.patient_id),
        "resolved": contradiction.resolved,
        "decision": contradiction.review_decision,
        "reviewed_by": contradiction.reviewed_by,
        "reviewed_at": contradiction.reviewed_at.isoformat() if contradiction.reviewed_at else None,
    }


@app.post("/emergency", dependencies=[Depends(require_security)])
def generate_emergency_card(request: Request, patient_id: UUID | None = None) -> dict:
    result = emergency_graph.invoke({"patient_id": resolve_patient_id(patient_id, request)})
    return {"status": "generated", "graph": result}


@app.post("/translate", dependencies=[Depends(require_security)])
def translate_output(request: Request, patient_id: UUID | None = None, language: str = "en") -> dict:
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported language; choose one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}",
        )
    result = language_graph.invoke({
        "patient_id": resolve_patient_id(patient_id, request),
        "target_language": language,
    })
    return {"status": "generated", "language": language, "graph": result}


def _sse_stream(chunks):
    try:
        for chunk in chunks:
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"
    except GenerationError as exc:
        yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"


@app.post("/brief/stream", dependencies=[Depends(require_security)])
def stream_doctor_brief_output(request: Request, patient_id: UUID | None = None) -> StreamingResponse:
    resolved_id = resolve_patient_id(patient_id, request)
    return StreamingResponse(
        _sse_stream(stream_doctor_brief({"patient_id": resolved_id})),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/emergency/stream", dependencies=[Depends(require_security)])
def stream_emergency_output(request: Request, patient_id: UUID | None = None) -> StreamingResponse:
    resolved_id = resolve_patient_id(patient_id, request)
    return StreamingResponse(
        _sse_stream(stream_emergency({"patient_id": resolved_id})),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/translate/stream", dependencies=[Depends(require_security)])
def stream_translation_output(
    request: Request, patient_id: UUID | None = None, language: str = "en"
) -> StreamingResponse:
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=422, detail="Unsupported language; choose one of: en, hi, kn")
    resolved_id = resolve_patient_id(patient_id, request)
    return StreamingResponse(
        _sse_stream(stream_language({"patient_id": resolved_id, "target_language": language})),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
