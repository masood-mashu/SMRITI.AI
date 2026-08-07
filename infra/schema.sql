CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE patients (
    patient_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reports (
    report_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     UUID NOT NULL REFERENCES patients(patient_id),
    source_type    TEXT NOT NULL,
    uploaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    file_url       TEXT,
    raw_extraction JSONB
);

CREATE TABLE health_facts (
    fact_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id             UUID NOT NULL REFERENCES patients(patient_id),
    report_id              UUID REFERENCES reports(report_id),
    fact_type              TEXT NOT NULL,
    fact_key               TEXT NOT NULL,
    fact_value             TEXT NOT NULL,
    unit                   TEXT,
    status                 TEXT NOT NULL DEFAULT 'active',
    is_emergency_relevant  BOOLEAN NOT NULL DEFAULT false,
    effective_date         DATE NOT NULL,
    recorded_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_by          UUID REFERENCES health_facts(fact_id),
    confidence             REAL
);

CREATE UNIQUE INDEX idx_facts_current ON health_facts (patient_id, fact_key) WHERE superseded_by IS NULL;
CREATE INDEX idx_facts_timeline ON health_facts (patient_id, effective_date);

CREATE TABLE contradictions (
    contradiction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id       UUID NOT NULL REFERENCES patients(patient_id),
    fact_id_older    UUID NOT NULL REFERENCES health_facts(fact_id),
    fact_id_newer    UUID NOT NULL REFERENCES health_facts(fact_id),
    description      TEXT NOT NULL,
    detected_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved         BOOLEAN NOT NULL DEFAULT false,
    review_decision  TEXT,
    reviewer_note    TEXT,
    reviewed_at      TIMESTAMPTZ,
    reviewed_by      TEXT
);
