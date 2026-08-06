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

The upload endpoint is available at `POST /reports` and currently returns a stub graph result. No Gemini calls, streaming, or persistence logic is implemented yet.

## Structure

- `backend/app/models.py` — SQLModel mappings for the append-only Postgres schema.
- `backend/app/graph.py` — five-node LangGraph skeleton.
- `backend/app/main.py` — FastAPI upload endpoint.
- `frontend/streamlit_app.py` — minimal upload client.
- `infra/schema.sql` — reference DDL matching the project context exactly.

The architecture JSON labels the Memory Agent's database edge as `out-agents` even though the label says `Fan-out State`. The implementation treats that as a diagram-port naming issue: Memory owns persistence, then fans out to the three downstream nodes.

