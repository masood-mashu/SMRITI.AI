# Smriti AI

Smriti is a patient-owned health-memory application. It turns medical reports
into structured health facts, keeps a longitudinal timeline, detects possible
contradictions, and generates a Doctor Brief, Emergency Card, or translation.

The repository is configured for a Vercel deployment with a vanilla frontend,
FastAPI serverless API, Neon PostgreSQL persistence, Auth0 authentication, and
optional Gemini model calls.

## Current architecture

```text
Browser
  └── public/index.html
        └── /api/* rewrite
              └── api/index.py
                    └── backend/app/main.py
                          ├── Neon PostgreSQL
                          ├── Auth0 / OIDC
                          ├── Gemini AI Studio or Vertex AI
                          └── local or cloud storage provider
```

The frontend never receives database credentials or AI API keys. Authentication
tokens are sent only to protected API routes.

## What happens when a report is added

1. The browser creates a stable demo patient ID in local storage, or receives
   the patient's identity from Auth0 when OIDC is enabled.
2. The frontend sends the report as multipart form data to `POST /api/reports`.
3. FastAPI validates the file type, size, and demo/production policy.
4. The configured PII scrubber removes supported email addresses and phone
   numbers before the report is stored or sent to an AI provider.
5. The report is stored through the configured storage provider and an
   ingestion job is created in PostgreSQL.
6. Synchronous demo mode processes the job during the request. Production can
   dispatch it to Cloud Tasks.
7. The extractor returns structured facts. The memory graph stores the report,
   appends new facts, supersedes changed current facts, and records
   contradictions.
8. The timeline reloads from PostgreSQL. Output buttons read current facts and
   generate deterministic text or Gemini output depending on configuration.

## End-to-end audit status

The local repository audit completed on 2026-08-08:

- 53 backend tests passed.
- Ruff reported no issues for `backend`, `api`, and `tests`.
- Python bytecode compilation passed for `backend` and `api`.
- Frontend JavaScript syntax validation passed.
- `git diff --check` passed.
- `pip-audit` could not complete because this environment could not reach
  PyPI; it did not report a vulnerability result.

The deployed Vercel smoke check must still be run from an unrestricted browser:

```text
GET  https://smriti-ai-livid.vercel.app/api/health
GET  https://smriti-ai-livid.vercel.app/api/health/ready
POST https://smriti-ai-livid.vercel.app/api/reports
```

`/api/health` confirms that the Vercel function imports. `/api/health/ready`
now confirms both the Neon connection and the presence of all five required
application tables. A successful report request still requires the schema,
storage, ingestion provider, and selected extractor to work together.

## Main technology stack

- Frontend: semantic HTML, CSS, and browser JavaScript
- Backend: Python, FastAPI, SQLModel, LangGraph-style processing graphs
- Database: Neon PostgreSQL with `psycopg`
- Deployment: Vercel Python Functions and static hosting
- Authentication: Auth0 OIDC with bearer-token validation
- AI: deterministic demo providers, Gemini API key, or Vertex AI
- Privacy: regex PII scrubbing for the demo; stricter providers can be enabled
- Testing: Pytest backend suite and static frontend checks

See [DEMO_TECH_STACK.md](DEMO_TECH_STACK.md) for the complete file map and
presentation checklist.

## Production setup

### 1. Create the Neon database

Create a Neon PostgreSQL project, copy its connection string into Vercel as
`DATABASE_URL`, and run the complete schema from
[database/schema.sql](database/schema.sql) in the Neon SQL Editor.

Set:

```env
DB_AUTO_CREATE=false
```

Never commit or share the database connection string. Rotate the Neon password
if it has ever been exposed.

### 2. Configure Vercel

Use the repository root as the Vercel Root Directory. Leave Build Command and
Output Directory empty. Vercel detects `api/index.py` automatically.

For a demo using Neon and deterministic extraction:

```env
SMRITI_ENV=demo
SMRITI_DEMO_MODE=true
DATABASE_URL=postgresql://...
DB_AUTO_CREATE=false
INGESTION_QUEUE_PROVIDER=sync
EXTRACTION_PROVIDER=stub
OUTPUT_PROVIDER=stub
PII_PROVIDER=regex
AUTH_ENABLED=false
PHI_STRICT=false
RATE_LIMIT_BACKEND=memory
```

After changing environment variables, redeploy the project. Use separate
Preview and Production values when testing branches.

### 3. Enable real Gemini calls

Create a Google AI Studio API key and add it only to Vercel:

```env
GEMINI_API_KEY=your_key
EXTRACTION_PROVIDER=gemini
OUTPUT_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
```

With this configuration, synthetic report text can still be used for the demo,
but extraction and generated outputs are made through Gemini. The key must not
be placed in `public/index.html`, `.env.example`, or any public environment
variable.

Vertex AI is also supported with:

```env
EXTRACTION_PROVIDER=vertex
OUTPUT_PROVIDER=vertex
GOOGLE_CLOUD_PROJECT=your_project
GOOGLE_CLOUD_LOCATION=global
```

### 4. Enable Auth0

Create an Auth0 Single Page Application and API, then configure the callback,
logout, and web-origin URLs to match the Vercel domain. Set:

```env
AUTH_ENABLED=true
AUTH_MODE=oidc
AUTH0_CLIENT_ID=your_client_id
OIDC_ISSUER=https://your-tenant.us.auth0.com/
OIDC_AUDIENCE=https://api.smriti.ai
```

Keep `AUTH_ENABLED=false` until the Auth0 application and API are fully
configured. The frontend signs users in through Auth0 and the backend maps the
stable OIDC subject to the user's patient history.

## Demo flow

1. Open the Vercel URL.
2. Click **Add a report**.
3. Submit the prepared synthetic report.
4. Confirm the facts appear in **Health memory**.
5. Generate the **Doctor brief** and **Emergency card**.
6. Select Hindi or Kannada and click **Translate**.

The demo is an organizational aid, not a diagnosis. Do not upload real patient
information to the synthetic demo configuration.

## Current limitations

- The shipped frontend presents the prepared synthetic text report in demo
  mode. Outside demo mode it also exposes a file picker for `.txt`, PDF, PNG,
  and JPEG reports, subject to the active privacy and signature settings.
- The demo defaults to deterministic fixture extraction and deterministic
  output. Real Gemini calls require `GEMINI_API_KEY` and the provider variables
  described above.
- Regex PII scrubbing currently targets email addresses and phone numbers. It
  is not a complete medical-privacy redaction system.
- Strict PHI mode currently allows text reports only because multimodal PII
  redaction is not complete.
- Contradiction review, deletion, MCP tools, and streaming routes exist in the
  backend but are not all exposed as buttons in the shipped frontend.
- Vercel local storage is temporary. Durable report files require encrypted
  GCS configuration; Neon stores the structured memory and report references.
- Non-production mode may store raw extracted JSON for debugging. Production
  configuration disables raw extraction storage by default.
- Demo mode uses browser-local patient identity and memory access is disabled
  only when Auth0 is explicitly enabled. Keep `AUTH_ENABLED=false` only for
  synthetic presentations.

## API routes

- `GET /api/health` — function health check
- `GET /api/health/ready` — database readiness check
- `GET /api/auth/config` — browser-safe Auth0 configuration
- `GET /api/runtime/config` — non-secret provider flags
- `POST /api/reports` — upload and process a report
- `GET /api/timeline` — retrieve saved facts and contradictions
- `POST /api/brief` — generate a Doctor Brief
- `POST /api/emergency` — generate an Emergency Card
- `POST /api/translate` — generate a translated output

## Troubleshooting

### `500 FUNCTION_INVOCATION_FAILED`

Check Vercel Runtime Logs, then verify:

1. `DATABASE_URL` is present in the same Vercel environment as the deployment.
2. `database/schema.sql` was executed in the Neon branch used by that URL.
3. `GET /api/health/ready` returns `{"status":"ready"}`. If tables are
   missing, it now reports their names directly.
4. `psycopg[binary]` is installed by the deployment.
5. `GEMINI_API_KEY` and provider names are correct if real AI is enabled.

The report endpoint now returns an actionable database or ingestion message
instead of hiding the failure behind a generic response.

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:SMRITI_ENV="demo"
$env:SMRITI_DEMO_MODE="true"
$env:INGESTION_QUEUE_PROVIDER="sync"
$env:EXTRACTION_PROVIDER="stub"
$env:OUTPUT_PROVIDER="stub"
$env:PII_PROVIDER="regex"
$env:AUTH_ENABLED="false"
$env:DATABASE_URL="sqlite:///./smriti.db"
uvicorn backend.app.main:app --reload --port 8000
```

The local API is available at `http://localhost:8000`. The deployed frontend
uses `/api/*` through the Vercel rewrite.

## Repository layout

```text
api/index.py              Vercel Python Function entrypoint
backend/app/              FastAPI app, providers, graphs, and persistence
database/schema.sql       Neon PostgreSQL schema
public/index.html         Vercel frontend
requirements.txt          Runtime dependencies
vercel.json               Vercel routing and function configuration
DEMO_TECH_STACK.md        Detailed stack and presentation guide
tests/                    Backend verification suite
```

The repository intentionally contains only the Vercel deployment path and its
required backend and verification files.
