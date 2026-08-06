# Product Requirements Document: Smriti AI Health Memory

## 1. Product summary

Smriti is a patient-owned health memory application. It converts uploaded
medical reports into a structured, longitudinal memory, preserves changes over
time, highlights contradictions, and produces on-demand summaries for patients
and clinicians.

Smriti is not a diagnostic, treatment, or emergency dispatch system.

## 2. Problem and users

Patients and caregivers often carry fragmented reports across hospitals and
specialists. Important allergies, medications, conditions, and lab history can
be missed or repeatedly reconstructed.

Primary users are patients and caregivers. Secondary consumers are doctors and
emergency responders receiving patient-authorized summaries.

## 3. Product goals

1. Build cumulative, patient-owned health memory.
2. Preserve history instead of overwriting prior facts.
3. Make contradictions visible for human review.
4. Provide concise Doctor Brief and Emergency outputs.
5. Explain recorded information in plain language and selected regional
   languages.
6. Protect patient isolation, privacy, and auditability.

## 4. Current product behavior

### 4.1 Report ingestion

The Streamlit client uploads PDF, image, or text reports to `POST /reports`.
The LangGraph ingestion path is:

```text
Report Understanding Agent -> Memory Agent -> persisted timeline
```

The fixture extractor is deterministic and intended for local demos. The
Vertex Gemini extractor is an opt-in provider. Upload does not automatically
run the output agents.

### 4.2 Memory

The Memory Agent writes to PostgreSQL through SQLModel. Facts are append-only:
when a value changes, a new fact is inserted and the prior fact points to it
through `superseded_by`. Contradictions are stored separately for review.

### 4.3 On-demand outputs

- `POST /brief` - Doctor Brief
- `POST /emergency` - Emergency information
- `POST /translate?language=hi` - Language output

Deterministic output providers are the default. Vertex generation is opt-in.

### 4.4 Context and interoperability

`POST /mcp` exposes JSON-RPC methods for current facts, emergency facts, and
contradictions. The backend also provides Google ADK-compatible Python tool
functions and an optional `FunctionTool` registration helper.

## 5. Functional requirements

### Must have

- Accept report uploads with type and size validation.
- Associate every report and fact with a patient.
- Store reports, facts, and contradictions in PostgreSQL.
- Preserve fact history with `superseded_by`.
- Display a timeline of current and superseded values.
- Generate Doctor Brief, Emergency, and Language outputs on demand.
- Enforce authenticated patient ownership in production.
- Provide health/readiness endpoints and structured request metadata.
- Provide local fixture mode without real patient data.

### Planned enhancements

- Streaming explanation and output responses.
- Native Vertex multimodal extraction after cloud billing and credentials are
  available.
- Vector Search for semantic history retrieval.
- Richer relationships between facts and clinical events.
- Clinician sharing and explicit patient consent workflows.

## 6. Non-functional requirements

- PostgreSQL is the production source of truth.
- Alembic migrations must run before application startup.
- Production rate limiting must be distributed through Redis.
- OIDC JWT validation must check issuer, audience, signature, expiry, and the
  patient ownership claim.
- Logs and audit events must not include report contents.
- Optional OTLP tracing must be configurable without changing application code.
- Required providers must fail closed when unavailable.
- A deterministic local path must remain available for demos and tests.

## 7. Architecture

```text
Streamlit
   |
FastAPI + security + request telemetry
   |
LangGraph ingestion: Report Understanding -> Memory
   |                         |
   |                    PostgreSQL / Alembic
   |
On-demand graphs: Doctor Brief | Emergency | Language
   |
MCP JSON-RPC context tools / optional ADK tools
```

The canonical architecture files are under `architecture/2nd arc/`. The
Memory Agent's output is intentionally the persistence boundary; downstream
outputs are invoked separately rather than treated as automatic fan-out.

## 8. Technology decisions

- Backend: FastAPI, LangGraph, SQLModel, PostgreSQL, Alembic
- Frontend: Streamlit
- AI provider boundary: Google Gen AI SDK through Vertex adapters
- Storage: local development storage or optional Google Cloud Storage
- Authentication: local static token or production OIDC JWT
- Rate limiting: in-memory development fallback or Redis in production
- Interoperability: MCP-compatible JSON-RPC endpoint and optional Google ADK
  tool wrappers
- Audit: structured local logs or optional BigQuery sink
- Tracing: OpenTelemetry API/SDK with optional OTLP HTTP exporter
- Deployment: Docker Compose for local production-shaped validation; Cloud Run
  remains a deployment task, not a claimed live environment

## 9. Data model

The required tables are:

- `patients`: patient identity and creation time
- `reports`: source metadata and raw extraction JSONB
- `health_facts`: typed facts, dates, confidence, emergency flag, and
  `superseded_by`
- `contradictions`: older/newer fact references and review state

The partial index on current facts is preserved:

```sql
WHERE superseded_by IS NULL
```

## 10. API contract

- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `POST /reports`
- `GET /timeline`
- `POST /brief`
- `POST /emergency`
- `POST /translate`
- `POST /mcp`

Streaming endpoints and WebSockets are not part of the current contract.

## 11. Security and safety

Development may use a static bearer token or no authentication. Production
must use OIDC, Redis rate limiting, and patient ownership enforcement.

Every generated output must organize recorded information. It must not
diagnose, prescribe, or silently resolve a contradiction.

## 12. Operations and verification

Local verification includes unit and API tests, PostgreSQL migration
upgrade/downgrade/reapply, PostgreSQL-backed application tests, Redis-backed
Compose startup, authenticated and unauthenticated API checks, fixture upload,
timeline, MCP, Doctor Brief, Emergency, Language, and frontend availability.

Cloud smoke tests require project credentials, enabled services, and billing.
The current project has not claimed successful paid Vertex execution.

## 13. Roadmap

1. Select and configure an OIDC provider for the deployed environment.
2. Add Cloud Run deployment and secret-management manifests.
3. Enable and evaluate Vertex Gemini/Gemma with approved billing and data
   controls.
4. Add streaming only after request/response behavior is stable.
5. Add Vector Search only when timeline retrieval needs semantic search.
6. Add clinician sharing, consent, retention, and deletion workflows.
7. Establish production SLOs, alerting, backup/restore drills, and security
   review.
