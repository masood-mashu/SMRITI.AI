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

The upload endpoint is available at `POST /reports` and runs only the Report Understanding -> Memory ingestion path. Use `POST /reports?fixture=true` for the opt-in synthetic development profile; real uploads currently remain extraction stubs. The timeline is available at `GET /timeline`. On-demand stub endpoints are available at `POST /brief`, `POST /emergency`, and `POST /translate?language=hi`.

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

To explicitly test Vertex extraction against one local report, configure Application Default Credentials and run `python scripts/vertex_smoke.py path/to/report.pdf`.
