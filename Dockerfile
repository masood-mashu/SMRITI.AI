# Multi-platform index digest verified against Docker Hub on 2026-08-08.
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md requirements.lock alembic.ini ./
COPY backend ./backend
COPY frontend ./frontend
COPY infra ./infra

RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .

RUN addgroup --system smriti && adduser --system --ingroup smriti smriti \
    && mkdir -p /app/.data/uploads \
    && chown -R smriti:smriti /app
USER smriti

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
