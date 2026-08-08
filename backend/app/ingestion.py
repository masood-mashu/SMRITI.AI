"""Durable ingestion dispatch and worker execution."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os
from hmac import compare_digest
from uuid import UUID

import requests
from sqlmodel import select

from .db import session_scope
from .extractor import ExtractionError, ProviderConfigurationError
from .graph import smriti_ingestion_graph
from .models import IngestionJob
from .repositories import update_ingestion_job
from .storage import StorageError, get_storage


class QueueError(RuntimeError):
    """Raised when an ingestion job cannot be dispatched."""


@dataclass(frozen=True)
class QueueConfig:
    provider: str
    project: str | None
    location: str | None
    queue: str | None
    target_url: str | None
    worker_token: str | None


def queue_config() -> QueueConfig:
    environment = os.getenv("SMRITI_ENV", "development").lower()
    demo_mode = os.getenv("SMRITI_DEMO_MODE", "false").lower() in {"1", "true", "yes", "on"}
    return QueueConfig(
        provider=os.getenv(
            "INGESTION_QUEUE_PROVIDER",
            "sync" if demo_mode or environment == "demo" else ("cloud_tasks" if environment == "production" else "inline"),
        ).lower(),
        project=os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("INGESTION_QUEUE_LOCATION"),
        queue=os.getenv("INGESTION_QUEUE_NAME"),
        target_url=os.getenv("INGESTION_WORKER_URL"),
        worker_token=os.getenv("INGESTION_WORKER_TOKEN") or None,
    )


def _cloud_tasks_headers() -> dict[str, str]:
    try:
        import google.auth
        from google.auth.transport.requests import Request as GoogleAuthRequest

        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not credentials.valid:
            credentials.refresh(GoogleAuthRequest())
        if not credentials.token:
            raise QueueError("Google credentials did not provide an access token")
        return {"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"}
    except QueueError:
        raise
    except Exception as exc:
        raise QueueError("Cloud Tasks credentials are unavailable") from exc


def _enqueue_cloud_task(job_id: UUID, config: QueueConfig) -> None:
    required = {
        "GCP_PROJECT": config.project,
        "INGESTION_QUEUE_LOCATION": config.location,
        "INGESTION_QUEUE_NAME": config.queue,
        "INGESTION_WORKER_URL": config.target_url,
        "INGESTION_WORKER_TOKEN": config.worker_token,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise QueueError("Cloud Tasks configuration is incomplete: " + ", ".join(missing))
    parent = f"projects/{config.project}/locations/{config.location}/queues/{config.queue}"
    task = {
        "task": {
            "httpRequest": {
                "httpMethod": "POST",
                "url": f"{config.target_url.rstrip('/')}/internal/ingestion-jobs/{job_id}/process",
                "headers": {
                    "Content-Type": "application/json",
                    "X-Smriti-Worker-Token": config.worker_token,
                },
                "body": base64.b64encode(json.dumps({"job_id": str(job_id)}).encode()).decode(),
            }
        }
    }
    response = requests.post(
        f"https://cloudtasks.googleapis.com/v2/{parent}:create",
        headers=_cloud_tasks_headers(),
        json=task,
        timeout=10,
    )
    if response.status_code >= 300:
        raise QueueError(f"Cloud Tasks rejected ingestion job ({response.status_code})")


def enqueue_ingestion_job(job_id: UUID) -> None:
    config = queue_config()
    if config.provider in {"inline", "sync"}:
        return
    if config.provider == "cloud_tasks":
        _enqueue_cloud_task(job_id, config)
        return
    raise QueueError(f"Unsupported ingestion queue provider: {config.provider}")


def process_ingestion_job(job_id: UUID) -> None:
    """Claim and execute one job; safe to retry after worker failure."""
    with session_scope() as session:
        job = session.exec(
            select(IngestionJob).where(IngestionJob.job_id == job_id).with_for_update()
        ).first()
        if job is None or job.status == "succeeded":
            return
        job.status = "running"
        session.add(job)
        file_url = job.file_url
        patient_id = job.patient_id
        filename = job.filename
        content_type = job.content_type
        source_type = job.source_type
        use_fixture = job.use_fixture
        pii_redactions = job.pii_redactions
        pii_provider = job.pii_provider

    if not file_url:
        _fail_job(job_id, "Ingestion job has no stored report")
        return
    try:
        content = get_storage().read(file_url)
        result = smriti_ingestion_graph.invoke({
            "patient_id": str(patient_id),
            "filename": filename,
            "content_type": content_type,
            "source_type": source_type,
            "use_fixture": use_fixture,
            "file_url": file_url,
            "report_bytes": content,
            "report_is_scrubbed": True,
            "pii_redactions": pii_redactions,
            "pii_provider": pii_provider,
        })
        with session_scope() as session:
            update_ingestion_job(session, job_id, status="succeeded", report_id=UUID(result["report_id"]))
    except (ProviderConfigurationError, ExtractionError, StorageError, RuntimeError) as exc:
        _fail_job(job_id, str(exc))
    except Exception as exc:
        _fail_job(job_id, f"Ingestion failed: {type(exc).__name__}")


def _fail_job(job_id: UUID, error: str) -> None:
    with session_scope() as session:
        job = session.get(IngestionJob, job_id)
        file_url = job.file_url if job else None
        update_ingestion_job(session, job_id, status="failed", error=error)
    if file_url:
        try:
            get_storage().delete(file_url)
        except StorageError:
            pass


def validate_worker_token(provided: str | None) -> bool:
    expected = queue_config().worker_token
    return bool(expected and provided and compare_digest(provided, expected))
