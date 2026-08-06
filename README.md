# Smriti

Smriti is a patient-owned health memory application. It turns uploaded medical
reports into a longitudinal, append-only timeline and provides on-demand
Doctor Brief, Emergency, and Language outputs.

The current implementation is a production-oriented prototype: the local
fixture path is fully runnable, while Vertex/Gemma, OIDC, BigQuery, AI Studio,
and OTLP services are opt-in integrations.

## Architecture

- FastAPI backend in `backend/app/`
- Streamlit frontend in `frontend/`
- LangGraph ingestion graph: Report Understanding -> Memory
- Separate on-demand graphs for Doctor Brief, Emergency, and Language
- PostgreSQL source of truth with SQLModel and Alembic
- Redis-backed production rate limiting
- Append-only facts with `superseded_by` history and contradiction records
- JSON-RPC MCP endpoint at `POST /mcp`
- Optional Google ADK tool wrappers in `backend/app/adk_tools.py`

Upload does not eagerly run all output agents. Outputs are generated only when
their endpoint is called, matching the patient interaction flow.

## Run locally

Development with SQLite and deterministic fixture data:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:DB_AUTO_CREATE="true"
$env:RATE_LIMIT_BACKEND="memory"
uvicorn backend.app.main:app --reload --port 8000
streamlit run frontend/streamlit_app.py
```

Use the synthetic, no-PII sample at `samples/synthetic_medical_report.txt`.

For the production-shaped local stack, start Docker Desktop and run:

```powershell
$env:SMRITI_API_TOKEN="replace-with-a-local-secret"
docker compose up --build
```

This starts PostgreSQL, Redis, an Alembic migration job, FastAPI, and
Streamlit. The API is available at `http://localhost:8000`; the frontend is
available at `http://localhost:8501`.

## API

- `GET /health` and `GET /health/live` - liveness
- `GET /health/ready` - database readiness
- `POST /reports` - upload a report; use `fixture=true` only for development
- `GET /timeline` - current and superseded facts plus contradictions
- `POST /brief` - generate Doctor Brief on demand
- `POST /emergency` - generate Emergency output on demand
- `POST /translate?language=hi` - generate Language output on demand
- `POST /mcp` - MCP-compatible JSON-RPC endpoint

Protected endpoints accept `Authorization: Bearer <token>` when authentication
is enabled. Production OIDC mode requires a JWT `patient_id` claim and rejects
cross-patient access.

## Configuration

Copy `.env.example` and adjust values for the target environment.

Important production settings:

```env
SMRITI_ENV=production
DATABASE_URL=postgresql+psycopg://...
DB_AUTO_CREATE=false
AUTH_ENABLED=true
AUTH_MODE=oidc
OIDC_ISSUER=https://...
OIDC_AUDIENCE=smriti-api
OIDC_JWKS_URL=https://.../.well-known/jwks.json
RATE_LIMIT_BACKEND=redis
REDIS_URL=redis://...
STORAGE_PROVIDER=local
STORAGE_ENCRYPTION_REQUIRED=true
STORAGE_ENCRYPTION_KEY=<base64-fernet-key>
STORAGE_RETENTION_DAYS=30
```

For local/demo authentication, use `AUTH_MODE=token` and
`SMRITI_API_TOKEN`. Never commit real credentials.

If local file storage is used in production, provide a Fernet key through a
secret manager and set a retention window. GCS storage should use the bucket's
server-side encryption and lifecycle policies.

## Optional integrations

- `EXTRACTION_PROVIDER=vertex` enables the Vertex Gemini multimodal extractor.
- `OUTPUT_PROVIDER=vertex` enables Vertex generation for the three output agents.
- `PII_PROVIDER=vertex_gemma` enables the Vertex Gemma text PII scrubber.
- `AUDIT_SINK=bigquery` enables BigQuery audit delivery.
- `PROMPT_PROVIDER=ai_studio` uses the configured `AI_STUDIO_PROMPT_URL`.
- `OTEL_ENABLED=true` enables OTLP tracing and requires
  `OTEL_EXPORTER_OTLP_ENDPOINT`.
- `pip install -e ".[adk]"` installs the optional Google ADK runtime; the
  tool functions remain usable without that extra.

Vertex calls require Google Cloud credentials, an enabled Vertex API, and an
active billing configuration. Without those, use the fixture and deterministic
providers. No real patient data is required for local verification.

## Database

Production schema changes use Alembic:

```powershell
$env:DATABASE_URL="postgresql+psycopg://..."
.\.venv\Scripts\alembic.exe upgrade head
```

`infra/schema.sql` remains the canonical reference DDL. The migration preserves
the required tables: `patients`, `reports`, `health_facts`, and
`contradictions`, including the partial current-facts index.

## Verification

Run the full local suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit
.\.venv\Scripts\python.exe -m bandit -r backend -ll
.\.venv\Scripts\python.exe -m ruff check backend frontend tests
```

The suite covers schema persistence, append-only supersession, security,
patient isolation, MCP, provider adapters, and the complete fixture flow.
`requirements.lock` pins the verified development environment, and GitHub
Actions installs it before running dependency checks, tests, and a container
build.

## Safety and current limits

Smriti is an organizational and explanatory aid, not a diagnostic or treatment
system. Outputs must preserve recorded facts and surface uncertainty or
contradictions for human review.

Streaming responses, Vertex Vector Search, Cloud Run deployment manifests,
live AI Studio credentials, and live cloud-provider smoke tests remain roadmap
items. The current API intentionally uses request/response calls and on-demand
output generation.
