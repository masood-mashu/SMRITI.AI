# Smriti AI

Smriti is a patient-owned health memory demo. A synthetic medical report is
added to memory, converted into structured health facts, and used to produce a
timeline, Doctor Brief, Emergency Card, and language output.

## Deployment

The repository is configured for one deployment target: **Vercel**.

- Static frontend: `public/index.html`
- Python Function: `api/index.py`
- FastAPI application: `backend/app/main.py`
- API routing: `vercel.json`
- Runtime dependencies: `requirements.txt`

The Vercel path does not use Streamlit, Docker, PostgreSQL, Redis, Cloud Run,
Cloud Tasks, or live Google model credentials. It uses deterministic fixture
providers, temporary SQLite storage, synchronous ingestion, and temporary
filesystem storage so the demo is reliable and free to run.

See [DEMO_TECH_STACK.md](DEMO_TECH_STACK.md) for the complete stack-to-file
map, Vercel settings, environment variables, demo script, and checklist.

## Vercel setup

Use the repository root as the Vercel root directory. Leave the build and
output directory settings empty. Vercel detects `api/index.py` as the Python
Function and serves `public/` as static content.

Configure these environment variables in the Vercel project:

```env
SMRITI_DEMO_MODE=true
SMRITI_ENV=demo
INGESTION_QUEUE_PROVIDER=sync
EXTRACTION_PROVIDER=stub
OUTPUT_PROVIDER=stub
PII_PROVIDER=regex
AUTH_ENABLED=false
PHI_STRICT=false
STORAGE_PROVIDER=local
LOCAL_STORAGE_DIR=/tmp/smriti-demo-uploads
DATABASE_URL=sqlite:////tmp/smriti-demo.db
RATE_LIMIT_BACKEND=memory
```

The deployment is synthetic-data-only. Vercel temporary storage is not durable
and must not be used for real patient information.

Because SQLite and uploaded files live in Vercel's temporary `/tmp` filesystem,
the presentation should be run as one continuous session in the same browser.
The demo is intentionally a showcase path, not a durable multi-instance data
store.

## Demo flow

1. Open the Vercel URL.
2. Click **+ Add report**.
3. Submit the prefilled synthetic report.
4. Show the updated health timeline.
5. Generate Doctor Brief and Emergency Card.
6. Select Hindi or Kannada and generate the translation.

## API routes used by the frontend

- `GET /api/health`
- `POST /api/reports?fixture=true`
- `GET /api/timeline`
- `POST /api/brief`
- `POST /api/emergency`
- `POST /api/translate?language=hi|kn|en`

## Local verification

Create a Python environment, install the development package (which includes
the local Uvicorn runner), and run the API:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:SMRITI_DEMO_MODE="true"
$env:SMRITI_ENV="demo"
$env:INGESTION_QUEUE_PROVIDER="sync"
$env:EXTRACTION_PROVIDER="stub"
$env:OUTPUT_PROVIDER="stub"
$env:PII_PROVIDER="regex"
$env:AUTH_ENABLED="false"
$env:PHI_STRICT="false"
$env:STORAGE_PROVIDER="local"
$env:LOCAL_STORAGE_DIR=".data/uploads"
$env:DATABASE_URL="sqlite:///./smriti.db"
$env:RATE_LIMIT_BACKEND="memory"
uvicorn backend.app.main:app --reload --port 8000
```

For the deployed frontend, the browser calls `/api/*`. For local API-only
testing, use `http://localhost:8000` directly.

## Repository layout

```text
api/index.py              Vercel Python Function entrypoint
backend/app/              FastAPI app, graphs, persistence, and providers
public/index.html         Vercel frontend
requirements.txt          Vercel runtime dependencies
vercel.json               Vercel rewrites and function settings
DEMO_TECH_STACK.md        Demo deployment and presentation guide
tests/                    Backend verification suite
```

The repository intentionally contains only the Vercel demo deployment path and
the backend verification suite.
