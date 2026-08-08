# Smriti Demo: Tech Stack and Deployment Map

This document describes the demo path we should present on stage. The Vercel
demo does **not** use Streamlit. It uses a static HTML/JavaScript frontend and
a FastAPI Python serverless API.

## 1. Recommended demo architecture

```text
Browser
  |
  | serves the UI from /public/index.html
  | calls /api/*
  v
Vercel
  |-- Static frontend: public/index.html
  `-- Python Function: api/index.py
          |
          | imports
          v
      FastAPI application: backend/app/main.py
          |
          |-- SQLite database in /tmp
          |-- Local encrypted/un-encrypted file storage in /tmp
          |-- Synchronous fixture ingestion
          |-- Deterministic extraction and output providers
          `-- LangGraph ingestion/output graphs
```

For the stage demo, keep the data synthetic and deterministic. This avoids
depending on Google Cloud, Redis, background workers, or live model calls while
still showing the complete product flow: add report, update memory, view the
timeline, and generate Doctor Brief/Emergency/Language outputs.

## 2. Tech stack used in the Vercel demo

| Layer | Technology | What it does | Files used |
|---|---|---|---|
| Frontend | Vanilla HTML, CSS, JavaScript | Renders the demo UI, stores a browser demo patient ID, uploads the synthetic report, refreshes facts, and requests outputs | `public/index.html` |
| Hosting/routing | Vercel | Serves static files and routes `/api/*` requests to the Python Function | `vercel.json` |
| API | Python + FastAPI | Handles report upload, timeline, outputs, health checks, and security middleware | `api/index.py`, `backend/app/main.py` |
| Validation | Pydantic / FastAPI models | Validates upload metadata, query parameters, languages, and API payloads | `backend/app/main.py`, `backend/app/extractor.py` |
| Agent orchestration | LangGraph | Runs Report Understanding → Memory and the on-demand output graphs | `backend/app/graph.py` |
| Demo extraction | Deterministic fixture provider | Converts the sample report into known facts without an LLM call | `backend/app/extractor.py` |
| Real extraction | Gemini AI Studio API key or Vertex AI | Extracts structured facts from uploaded reports | `backend/app/extractor.py` |
| Demo generation | Deterministic stub output provider | Produces repeatable Doctor Brief, Emergency Card, and translation output without an LLM call | `backend/app/graph.py`, `backend/app/generation.py` |
| Real generation | Gemini AI Studio API key or Vertex AI | Generates the Doctor Brief, Emergency Card, and translation | `backend/app/generation.py`, `backend/app/graph.py` |
| Database | SQLite + SQLModel | Stores patients, reports, ingestion jobs, health facts, and contradictions | `backend/app/db.py`, `backend/app/models.py`, `backend/app/repositories.py` |
| File storage | Local filesystem storage | Temporarily stores the uploaded synthetic report in Vercel `/tmp` | `backend/app/storage.py` |
| Privacy | Regex PII scrubber | Removes basic email/phone patterns before persistence in demo mode | `backend/app/privacy.py` |
| Authentication | Disabled demo mode | Uses a browser-generated demo patient UUID; no login is needed for the judge flow | `backend/app/security.py`, `public/index.html` |
| Dependencies | Pinned Python packages | Installs the FastAPI, SQLModel, LangGraph, multipart upload, and security runtime | `requirements.txt` |

## 3. Files required for Vercel

These are the files that must be present in the deployed repository:

### Frontend

- `public/index.html` — the actual Vercel demo frontend. This is the page the
  judges open.

### API entrypoint and backend

- `api/index.py` — Vercel's Python Function entrypoint. It exposes the FastAPI
  app.
- `backend/app/main.py` — API routes such as `/reports`, `/timeline`,
  `/brief`, `/emergency`, and `/translate`.
- `backend/app/config.py` — environment-backed settings and production
  validation.
- `backend/app/db.py` — database engine and session management.
- `backend/app/models.py` — SQLModel database tables.
- `backend/app/repositories.py` — persistence and append-only fact merging.
- `backend/app/graph.py` — LangGraph agents and output generation.
- `backend/app/ingestion.py` — synchronous demo ingestion and job processing.
- `backend/app/extractor.py` — fixture extraction and optional Vertex adapter.
- `backend/app/generation.py` — deterministic output fallback and optional
  Vertex Gemini adapter.
- `backend/app/privacy.py` — demo PII scrubbing boundary.
- `backend/app/storage.py` — temporary local report storage.
- `backend/app/security.py` — demo/security checks and rate limiting.
- `backend/app/integrations.py` — prompt/provider integration boundary.
- `backend/app/observability.py` — request metrics, audit events, and tracing
  hooks.
- `backend/app/mcp_server.py` — MCP endpoint included by the API; not needed
  for the primary judge click path, but included by the backend import.

### Deployment and package configuration

- `vercel.json` — rewrites `/api/*` to `api/index.py` and sets the function
  timeout.
- `requirements.txt` — runtime dependencies Vercel installs.
- `pyproject.toml` — package metadata and development dependencies.
- `.vercelignore` — files excluded from the Vercel upload.

## 4. Vercel environment variables for the demo

### Project settings

- **Root Directory:** repository root (`D:\hackathon\smriti.ai` locally).
- **Framework Preset:** Other.
- **Build Command:** leave empty; Vercel detects `api/index.py` and serves
  `public/` as static content.
- **Output Directory:** leave empty.
- **Install Command:** use the default Python dependency install so
  `requirements.txt` is available to the Function.
- **Node.js:** not required for this demo.

Set these in Vercel Project Settings → Environment Variables. Use them for
Preview and Production if both environments will be used.

```env
SMRITI_DEMO_MODE=true
SMRITI_ENV=demo
INGESTION_QUEUE_PROVIDER=sync
EXTRACTION_PROVIDER=stub
OUTPUT_PROVIDER=stub
GEMINI_API_KEY=
PII_PROVIDER=regex
AUTH_ENABLED=false
PHI_STRICT=false
STORAGE_PROVIDER=local
LOCAL_STORAGE_DIR=/tmp/smriti-demo-uploads
DATABASE_URL=sqlite:////tmp/smriti-demo.db
RATE_LIMIT_BACKEND=memory
```

What these settings mean:

- `SMRITI_DEMO_MODE=true` restricts uploads to synthetic fixture mode.
- `SMRITI_ENV=demo` enables the demo configuration path.
- `INGESTION_QUEUE_PROVIDER=sync` processes the report during the request, so
  no Cloud Tasks worker is needed.
- `EXTRACTION_PROVIDER=stub` and `OUTPUT_PROVIDER=stub` keep the demo
  deterministic and do not require Google credentials. Set both to `gemini`
  and provide `GEMINI_API_KEY` to enable real Gemini calls.
- `GEMINI_API_KEY` is server-side only. Never add it to frontend code or expose
  it through a public environment variable.
- `PII_PROVIDER=regex` uses the local deterministic scrubber.
- `DATABASE_URL` and `LOCAL_STORAGE_DIR` point to temporary Vercel storage.
- `AUTH_ENABLED=false` keeps the judge flow login-free.

Vercel's filesystem is temporary. Do not use this configuration for real
patient information or as durable production storage. For a stage presentation,
add the report and inspect the timeline in one continuous browser session;
cold starts or separate function instances may not share `/tmp` state.

## 5. What is not used by the Vercel demo

The following are not part of the judge-facing Vercel path:

- `frontend/streamlit_app.py` — legacy/local Streamlit frontend; do not start
  it for the Vercel demo.
- `Dockerfile` and `docker-compose.yml` — local/container deployment path.
- PostgreSQL — replaced by temporary SQLite for the free demo.
- Redis — replaced by in-process memory rate limiting.
- Cloud Tasks — replaced by synchronous ingestion.
- Google Vertex AI/Gemini — replaced by fixture extraction and deterministic
  outputs.
- GCS, Cloud KMS, OIDC, BigQuery, and OTLP — optional production integrations,
  not required for the synthetic Vercel presentation.

## 6. Stage demo sequence

1. Open the Vercel URL.
2. Click **+ Add report** in the top-right navigation.
3. Leave the synthetic report text in the form and click **+ Add report**.
4. Show the updated health timeline and extracted facts.
5. Click **Doctor Brief** and explain that the output is generated from the
   patient's accumulated memory.
6. Click **Emergency Card** and highlight emergency-relevant facts.
7. Select Hindi or Kannada and click **Translate**.
8. Refresh the page only when demonstrating that the same browser demo patient
   identity is retained in `localStorage`.

## 7. Pre-demo verification checklist

- Confirm the Vercel deployment is using the repository root as its root
  directory.
- Confirm `public/index.html` loads without a 404.
- Confirm `GET /api/health` returns successfully.
- Add one synthetic report and verify that `/api/timeline` contains facts.
- Test Doctor Brief, Emergency Card, and Translate before presenting.
- Use synthetic data only; do not paste real patient data into the demo.
- Do not enable `SMRITI_ENV=production` for this Vercel demo configuration.

## 8. Repository scope

There is no separate Streamlit, Docker, Cloud Run, or database-migration
deployment directory in this repository. The remaining backend provider seams
are kept only where they are imported by the FastAPI application or useful for
safe demo behavior; the Vercel environment variables above select the
deterministic local implementations.
