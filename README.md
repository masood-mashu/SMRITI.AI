# Smriti

Initial skeleton for Smriti's FastAPI + LangGraph backend and Streamlit frontend.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn backend.app.main:app --reload --port 8000
streamlit run frontend/streamlit_app.py
```

The upload endpoint is available at `POST /reports` and runs only the Report Understanding -> Memory ingestion path. It accepts `patient_id`, `source_type`, and opt-in `fixture=true`. The timeline is available at `GET /timeline` and includes historical facts plus unresolved contradictions. On-demand stub endpoints are available at `POST /brief`, `POST /emergency`, and `POST /translate?language=hi`.

## Structure

- `backend/app/models.py` - SQLModel mappings for the append-only Postgres schema.
- `backend/app/graph.py` - five-agent LangGraph skeleton with separate ingestion and on-demand output graphs.
- `backend/app/main.py` - FastAPI upload and output endpoints.
- `backend/app/extractor.py` - fixture and Gemini provider contract.
- `backend/app/privacy.py` - Gemma PII-scrubbing provider boundary.
- `frontend/streamlit_app.py` - minimal upload client.
- `infra/schema.sql` - reference DDL matching the project context exactly.
- `architecture/2nd arc/` - canonical architecture JSON and rendered diagram.

The canonical architecture separates report ingestion from on-demand Doctor Brief, Emergency, and Language outputs while retaining the five-agent LangGraph design.

Real uploads use the Gemini provider stub by default and do not produce facts. Set `EXTRACTION_PROVIDER=vertex` and configure Google Cloud credentials to enable the Vertex Gemini adapter. The synthetic fixture is opt-in with `fixture=true`; it is intended only for local development.

Set `OUTPUT_PROVIDER=vertex` to opt into Vertex-backed Doctor Brief, Emergency Card, and Language generation. The output model IDs are configurable with `DOCTOR_BRIEF_MODEL`, `EMERGENCY_MODEL`, and `LANGUAGE_MODEL`; the deterministic outputs remain the default when billing or credentials are unavailable.

Phase 5 integration boundaries are available behind configuration: `PROMPT_PROVIDER=local` uses the local prompt registry, `PROMPT_PROVIDER=ai_studio` is reserved for the AI Studio registry client, `MCPContextGateway` exposes MCP-shaped context tools, `adk_tools.py` contains ADK-compatible memory tools, and `AUDIT_SINK=bigquery` enables the BigQuery audit sink. These cloud integrations are explicit and fail closed when credentials or services are missing; no live MCP server, ADK runtime, AI Studio registry, or Antigravity service is claimed by the local default.

Security is opt-in for local development. Set `AUTH_ENABLED=true` and `SMRITI_API_TOKEN` to require a bearer token; `RATE_LIMIT_PER_MINUTE` controls the per-process limiter. Request IDs, latency, and route metadata are logged without report content, and OpenTelemetry spans activate when an SDK/exporter is configured.

To explicitly test Vertex extraction against one local report, configure Application Default Credentials and run `python scripts/vertex_smoke.py path/to/report.pdf`.

For a no-PII local test input, use `samples/synthetic_medical_report.txt`.
