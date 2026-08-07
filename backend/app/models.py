"""SQLModel mappings for Smriti's append-only health memory schema."""

from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Patient(SQLModel, table=True):
    __tablename__ = "patients"
    patient_id: UUID = Field(default_factory=uuid4, primary_key=True)
    display_name: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class Report(SQLModel, table=True):
    __tablename__ = "reports"
    __table_args__ = (Index("idx_reports_patient", "patient_id", "uploaded_at"),)
    report_id: UUID = Field(default_factory=uuid4, primary_key=True)
    patient_id: UUID = Field(foreign_key="patients.patient_id", nullable=False)
    source_type: str = Field(sa_column=Column(Text, nullable=False))
    uploaded_at: datetime = Field(default_factory=utc_now, nullable=False)
    file_url: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    raw_extraction: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB().with_variant(JSON, "sqlite")),
    )


class IngestionJob(SQLModel, table=True):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (Index("idx_ingestion_jobs_patient_status", "patient_id", "status", "created_at"),)
    job_id: UUID = Field(default_factory=uuid4, primary_key=True)
    patient_id: UUID = Field(foreign_key="patients.patient_id", nullable=False)
    report_id: Optional[UUID] = Field(default=None, foreign_key="reports.report_id")
    file_url: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    source_type: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(default="pending", sa_column=Column(Text, nullable=False))
    error: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class HealthFact(SQLModel, table=True):
    __tablename__ = "health_facts"
    __table_args__ = (
        Index(
            "idx_facts_current",
            "patient_id",
            "fact_key",
            unique=True,
            postgresql_where=text("superseded_by IS NULL"),
            sqlite_where=text("superseded_by IS NULL"),
        ),
        Index("idx_facts_timeline", "patient_id", "effective_date"),
    )
    fact_id: UUID = Field(default_factory=uuid4, primary_key=True)
    patient_id: UUID = Field(foreign_key="patients.patient_id", nullable=False)
    report_id: Optional[UUID] = Field(default=None, foreign_key="reports.report_id")
    fact_type: str = Field(sa_column=Column(Text, nullable=False))
    fact_key: str = Field(sa_column=Column(Text, nullable=False))
    fact_value: str = Field(sa_column=Column(Text, nullable=False))
    unit: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(default="active", sa_column=Column(Text, nullable=False, server_default="active"))
    is_emergency_relevant: bool = Field(default=False, nullable=False)
    effective_date: date
    recorded_at: datetime = Field(default_factory=utc_now, nullable=False)
    superseded_by: Optional[UUID] = Field(default=None, foreign_key="health_facts.fact_id")
    confidence: Optional[float] = None


class Contradiction(SQLModel, table=True):
    __tablename__ = "contradictions"
    __table_args__ = (Index("idx_contradictions_patient", "patient_id", "detected_at"),)
    contradiction_id: UUID = Field(default_factory=uuid4, primary_key=True)
    patient_id: UUID = Field(foreign_key="patients.patient_id", nullable=False)
    fact_id_older: UUID = Field(foreign_key="health_facts.fact_id", nullable=False)
    fact_id_newer: UUID = Field(foreign_key="health_facts.fact_id", nullable=False)
    description: str = Field(sa_column=Column(Text, nullable=False))
    detected_at: datetime = Field(default_factory=utc_now, nullable=False)
    resolved: bool = Field(default=False, nullable=False)
    review_decision: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    reviewer_note: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    reviewed_at: Optional[datetime] = Field(default=None, nullable=True)
    reviewed_by: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
