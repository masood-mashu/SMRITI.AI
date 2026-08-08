-- Smriti persistent memory schema for Neon PostgreSQL.
-- Run this once in the Neon SQL Editor against the production branch.

CREATE TABLE IF NOT EXISTS patients (
    patient_id       UUID PRIMARY KEY,
    display_name     TEXT NOT NULL,
    external_subject TEXT UNIQUE,
    created_at       TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id       UUID PRIMARY KEY,
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    source_type     TEXT NOT NULL,
    uploaded_at     TIMESTAMPTZ NOT NULL,
    file_url        TEXT,
    raw_extraction  JSONB
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id          UUID PRIMARY KEY,
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    report_id       UUID REFERENCES reports(report_id),
    file_url        TEXT,
    filename        TEXT NOT NULL DEFAULT 'report',
    content_type    TEXT NOT NULL DEFAULT 'application/octet-stream',
    source_type     TEXT NOT NULL,
    use_fixture     BOOLEAN NOT NULL DEFAULT FALSE,
    pii_redactions  INTEGER NOT NULL DEFAULT 0,
    pii_provider    TEXT NOT NULL DEFAULT 'unknown',
    status          TEXT NOT NULL DEFAULT 'pending',
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS health_facts (
    fact_id              UUID PRIMARY KEY,
    patient_id           UUID NOT NULL REFERENCES patients(patient_id),
    report_id            UUID REFERENCES reports(report_id),
    fact_type            TEXT NOT NULL,
    fact_key             TEXT NOT NULL,
    fact_value           TEXT NOT NULL,
    unit                 TEXT,
    status               TEXT NOT NULL DEFAULT 'active',
    is_emergency_relevant BOOLEAN NOT NULL DEFAULT FALSE,
    effective_date       DATE NOT NULL,
    recorded_at          TIMESTAMPTZ NOT NULL,
    superseded_by        UUID REFERENCES health_facts(fact_id),
    confidence           REAL
);

CREATE TABLE IF NOT EXISTS contradictions (
    contradiction_id UUID PRIMARY KEY,
    patient_id       UUID NOT NULL REFERENCES patients(patient_id),
    fact_id_older    UUID NOT NULL REFERENCES health_facts(fact_id),
    fact_id_newer    UUID NOT NULL REFERENCES health_facts(fact_id),
    description      TEXT NOT NULL,
    detected_at      TIMESTAMPTZ NOT NULL,
    resolved         BOOLEAN NOT NULL DEFAULT FALSE,
    review_decision  TEXT,
    reviewer_note    TEXT,
    reviewed_at      TIMESTAMPTZ,
    reviewed_by      TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_external_subject
    ON patients (external_subject);

CREATE INDEX IF NOT EXISTS idx_reports_patient
    ON reports (patient_id, uploaded_at);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_patient_status
    ON ingestion_jobs (patient_id, status, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_current
    ON health_facts (patient_id, fact_key)
    WHERE superseded_by IS NULL;

CREATE INDEX IF NOT EXISTS idx_facts_timeline
    ON health_facts (patient_id, effective_date);

CREATE INDEX IF NOT EXISTS idx_contradictions_patient
    ON contradictions (patient_id, detected_at);
