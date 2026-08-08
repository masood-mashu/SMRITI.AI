# Smriti AI — Independent Production-Readiness Audit (Verified)

**Audited artifact:** `SMRITI_AI-main.zip`, branch `main` (no git history included)
**Audit date:** 2026-08-08
**Method:** Full source inspection + live execution against **real PostgreSQL 16 and real Redis 7** (installed in the audit sandbox from Ubuntu apt), not just SQLite/in-memory stand-ins. Docker and live Vertex AI were not available (no Docker daemon, no GCP credentials) and are marked NOT VERIFIABLE LOCALLY.

**Note on the audit already inside the repo:** The zip ships its own prior audit, `smriti-ai-production-readiness-audit_by_claude.md`, dated the same day, which explicitly ran only against SQLite (no Postgres/Redis/Docker available in that run). Running the same code against real Postgres surfaced a **critical bug that audit did not catch**, and two of its "CONFIRMED" findings (F‑01 metrics, F‑02 no ingestion queue) turned out to be **stale/incorrect against the code actually in this zip** — a Redis-backed metrics path and a real Cloud Tasks-based async ingestion queue both already exist. Treat that file as a partial, superseded reference rather than ground truth; the findings below were independently re-verified.

---

## A. Executive Verdict

| Question | Answer |
|---|---|
| Safe for local development? | **Yes** |
| Safe for demo (fixture/synthetic data only)? | **Yes** |
| Safe for controlled pilot? | **No — blocked** by F‑01 below |
| Safe for real patient data? | **No** |
| Safe for broad production? | **No** |

**Score: 5.5 / 10**
**Method:** mean of 10 equally-weighted categories (Architecture, Security/AuthZ, Privacy/PHI, AI Safety, Backend Correctness, DB/Migrations, Infra/Ops, Frontend Integration, Testing, Documentation Accuracy), each scored 0–10 on verified evidence only. No category is allowed to be offset by strength elsewhere, because a health-memory system can't be "carried" by good architecture if its core write path crashes in production. The two dominant drags are Backend Correctness (2/10 — the core supersession path is broken against the real production database) and AI Safety (4/10 — no live model validation possible, narrow eval set).

### Why this is lower than the bundled prior audit's 7.4/10
That score was computed entirely on SQLite, where SQLite's default (off) foreign-key enforcement silently hides a bug that fires on every real Postgres write to the append-only fact history — the feature that is the product's core differentiator (see F‑01). A number that doesn't survive contact with the target database isn't a usable release signal.

### Three strongest aspects (CONFIRMED)
1. **Fail-closed production config gate.** `backend/app/config.py:51-93` (`validate_production_settings`) refuses to boot under `SMRITI_ENV=production` unless OIDC auth, Redis rate limiting, Redis metrics, Cloud Tasks queue, strict PHI mode, upload signature checking, non-auto-create DB, and storage encryption/retention are all explicitly set. This is a genuinely disciplined pattern.
2. **Patient isolation (IDOR) is consistently enforced.** Every route that takes `patient_id` — REST (`main.py`, e.g. `resolve_patient_id` at `main.py:137-149`), and the MCP JSON-RPC surface (`mcp_server.py:88`) — routes through `enforce_patient_access`/`resolve_patient_id` (`security.py:71-83`), which rejects any OIDC-authenticated request whose token `patient_id` claim doesn't match the requested one. No endpoint was found that skips this check.
3. **Real async ingestion queue already exists**, contradicting the bundled audit's F‑02. `backend/app/ingestion.py` dispatches to Google Cloud Tasks in production (`_enqueue_cloud_task`, lines 66-98) and only runs inline via `BackgroundTasks` in development/test (`main.py:341-343`, gated on `queue_config().provider == "inline"`). A signed internal worker endpoint (`POST /internal/ingestion-jobs/{job_id}/process`, `main.py:278-283`) processes jobs out of the request/response cycle, authenticated by a constant-time-compared worker token (`ingestion.py:165-167`).

### Three most important weaknesses (CONFIRMED)
1. **The append-only fact-supersession path throws an unhandled `IntegrityError` on real PostgreSQL — every time.** This is the product's central mechanism (superseding old facts, recording contradictions) and it is broken against the actual target database. See F‑01.
2. **Every configuration that is safe for real PHI (`PHI_STRICT=true`) rejects all PDF and image uploads outright**, because the PII scrubber only redacts text content and hard-fails on binary content in strict mode (`privacy.py:41-45`, `104-106`). Since lab results, discharge summaries, and prescriptions are overwhelmingly PDFs or scans, the one safe-for-PHI configuration cannot actually ingest the reports the product exists to process. See F‑02.
3. **AI safety validation is minimal and entirely unverified live.** `evals/synthetic_extraction_cases.json` contains a small fixed synthetic set with no adversarial/prompt-injection cases, and no live Vertex Gemini/Gemma call has ever been exercised (no GCP credentials in any known audit run, including this one).

### Exact production blockers
- F‑01 (Critical) and F‑02 (High) below must be fixed before any pilot with real data.
- Live Vertex Gemini/Gemma behavior (extraction accuracy, prompt-injection resistance, redaction quality) is NOT VERIFIABLE LOCALLY and must be validated against a live endpoint with synthetic PHI-shaped text before real PHI is sent.
- Docker image build and non-root runtime behavior are NOT VERIFIABLE LOCALLY (no Docker daemon in this environment) and must be built and scanned in CI before deploy.

### What cannot be verified locally
- Live Vertex Gemini/Gemma calls (no GCP credentials).
- Container build, image size, non-root execution (no Docker daemon; egress is also restricted to a fixed domain allow-list that excludes Docker registries in this sandbox).
- Cloud Run behavior: cold starts, concurrency under `containerConcurrency`, multi-instance metric aggregation, IAM, KMS, Cloud Scheduler.
- Real-world latency, cost, or throughput figures.
- HIPAA/SOC2/compliance status — a legal/organizational determination, not a code property.

---

## B. Release Blockers

### F‑01 — Critical — Fact supersession violates a foreign key on real PostgreSQL
- **File/line:** `backend/app/repositories.py:135-154` (`persist_report_and_facts`)
- **Reproduction (verified live, not inferred):**
  ```
  createdb smriti_test; alembic upgrade head   # real Postgres 16
  pytest tests/test_memory.py tests/test_api.py -q
  # → sqlalchemy.exc.IntegrityError (psycopg.errors.ForeignKeyViolation)
  #   health_facts_superseded_by_fkey: Key (superseded_by)=(...) is not present in table "health_facts"
  ```
  2 of 49 tests fail this way against Postgres (`test_patient_deletion_removes_database_records_and_upload`, `test_contradiction_review_records_decision_without_mutating_facts`); all 49 pass on SQLite, which is why this was invisible in the SQLite-only prior audit and in local dev (`db.py:16-30` never enables `PRAGMA foreign_keys=ON`, so SQLite doesn't check the FK at all).
- **Root cause:** at `repositories.py:135-152`, the new `HealthFact` row (`fact = HealthFact(fact_id=uuid4(), ...)`) is constructed and its `fact_id` is assigned in Python, then `current.superseded_by = fact.fact_id` is set and **flushed** (line 152) *before* `session.add(fact)` (line 153) has ever added the new row to the session. On Postgres, the flush at line 152 tries to `UPDATE health_facts SET superseded_by = <new fact's uuid>` while that new fact row does not exist yet in the table, violating the FK constraint added in migration `0001_initial_schema`.
- **Impact:** Any time a patient's fact value changes across two reports (i.e., any real longitudinal use of the app — the entire point of the product), the request throws an unhandled 500 and no fact/contradiction is persisted. `DELETE /patients/{id}` and `POST /contradictions/{id}/review` also touch this code path indirectly and fail the same way in the test evidence above.
- **Fix:** reorder so the new fact is inserted before the update that references it:
  ```python
  fact = HealthFact(fact_id=uuid4(), ...)
  session.add(fact)
  session.flush()          # insert the new row first
  if current is not None:
      current.superseded_by = fact.fact_id
      session.flush()      # now the FK target exists
  ```
- **Verification test:** run the two failing tests (and ideally the whole suite) against a real Postgres `DATABASE_URL` in CI, not just SQLite — see F‑06 and the CI recommendation in E.
- **Must fix before:** demo (if demo ever touches Postgres instead of the SQLite fixture path — it should be assumed it eventually will), pilot, production. Not a blocker for the pure-SQLite fixture demo path.

### F‑02 — High — Strict PHI mode (the only production-safe mode) rejects all PDF/image uploads
- **File/line:** `backend/app/privacy.py:41-45` (`RegexPiiScrubber.scrub`), `104-106` (`VertexGemmaPiiScrubber.scrub`), both gated by `is_text_upload` (line 21-22).
- **Reproduction:** with `PHI_STRICT=true` (the production default per `config.py`/README) and `PII_PROVIDER` set to any provider, `POST /reports` with a `.pdf` or `.png` file body raises `PrivacyPolicyError` → HTTP 415, because no scrubber in this codebase performs PII redaction on binary/image content — they all fall back to a **text-only regex scrubber**, which itself refuses binary input when `strict=True`.
- **Impact:** `ALLOWED_CONTENT_TYPES`/`ALLOWED_SUFFIXES` (`main.py:70-71`) advertise PDF/PNG/JPG as accepted formats, and the README describes uploading "medical reports" generically, but the only configuration considered safe for real PHI cannot actually ingest the document types (scanned labs, discharge summaries, prescriptions) that make up the overwhelming majority of real-world medical reports. This is a product-completeness gap, not just a config nit — a controlled pilot with real reports would only be able to ingest plain-text uploads.
- **Fix:** either (a) implement true multimodal PII redaction (OCR + Gemma text redaction, or Vertex's multimodal PII detection) before storage for binary uploads, or (b) explicitly scope the product/pilot messaging to text uploads only until that exists, and gate PDF/image acceptance behind that capability rather than behind the general upload-format allow-list.
- **Verification test:** add a test that uploads a synthetic PDF with `PHI_STRICT=true` and a real (or realistically mocked) multimodal scrubber and asserts successful ingestion with redaction evidence.
- **Must fix before:** any pilot or production use with real reports. Not a blocker for a text-only or fixture-based demo.

---

## C. Findings Register

| ID | Status | Severity | Category | Finding | Evidence | Impact | Fix | Verification |
|----|--------|----------|----------|---------|----------|--------|-----|---------------|
| F‑01 | CONFIRMED (live Postgres) | Critical | Backend Correctness | Fact-supersession flush ordering violates `health_facts_superseded_by_fkey` on Postgres | `repositories.py:135-154`; reproduced via `pytest` against real Postgres 16 | Every longitudinal fact update / contradiction crashes with 500 in the target production DB | Insert new fact + flush before updating `current.superseded_by` | Re-run `tests/test_memory.py`, `tests/test_api.py` against Postgres |
| F‑02 | CONFIRMED | High | Product/Privacy | `PHI_STRICT=true` (production default) rejects all binary (PDF/image) uploads — only text works | `privacy.py:41-45,104-106`, `main.py:70-71` | The one safe-for-PHI config can't ingest real-world report formats | Build real multimodal redaction or scope product to text uploads | Upload a synthetic PDF under `PHI_STRICT=true` and assert success/redaction |
| F‑03 | CORRECTION to bundled audit | — | Backend Architecture | Bundled audit's F‑02 ("no background queue, synchronous invoke") is stale/incorrect against this code — a real Cloud Tasks-backed async queue exists | `ingestion.py:37-108`, internal worker endpoint `main.py:278-283` | Readers of the bundled audit would over-prioritize rebuilding something that already exists | N/A — documentation correction | Read `ingestion.py` directly |
| F‑04 | CORRECTION to bundled audit | — | Observability | Bundled audit's F‑01 ("metrics are process-local, CONFIRMED") is stale — a Redis-backed shared metrics path (`METRICS_BACKEND=redis`) already exists and is required by `validate_production_settings` | `observability.py:56-79`, `config.py` `required["METRICS_BACKEND"]` | Same as above | N/A — documentation correction | Read `observability.py` directly |
| F‑05 | CONFIRMED | Low | Security Hardening | 3 Bandit findings, all `B311` (non-crypto `random.uniform` used for retry-backoff jitter) | `extractor.py:181`, `generation.py:84,121` | None — this is correct use of `random` for jitter, not a security issue | No action needed; optionally `# nosec` with a comment | `bandit -r backend` |
| F‑06 | CONFIRMED | Medium | Testing/CI | The full test suite has only ever been run against SQLite in CI/prior audits; it was never run against Postgres before this audit, which is how F‑01 stayed hidden | No `DATABASE_URL=postgresql://...` step found in `.github/workflows/*` | Real production-database bugs can ship undetected | Add a Postgres service container to CI and run the full suite against it, not just SQLite | Inspect `.github/workflows/*.yml`; confirmed no Postgres test job present |
| F‑07 | CONFIRMED | Low | Testing | No test exercises the Redis-backed rate limiter or Redis-backed metrics path; running the suite with `RATE_LIMIT_BACKEND=redis` causes unrelated tests to fail with 429s because the suite's reset helper (`rate_limiter._events.clear()`) only clears the in-memory limiter, not Redis state | Reproduced: `RATE_LIMIT_BACKEND=redis pytest tests/test_security.py` → 2 failures from leaked rate-limit buckets | Redis rate limiting and Redis metrics are effectively untested despite being production-required | Add a dedicated Redis-backend test file that flushes Redis between tests | `redis-cli FLUSHALL` between tests, or a fixture that does so |
| F‑08 | CONFIRMED | Low | AI Safety/Eval | Synthetic extraction eval set has no adversarial/prompt-injection cases | `evals/synthetic_extraction_cases.json`, `scripts/run_extraction_eval.py` | Prompt-injection susceptibility via report content wouldn't be caught by CI | Add adversarial cases (e.g. embedded "ignore previous instructions...") and gate CI on them | `python scripts/run_extraction_eval.py` after expanding cases |
| F‑09 | NOT VERIFIABLE LOCALLY | — | AI Safety | No live Vertex Gemini/Gemma call has ever been exercised by any audit (no GCP credentials available) | `scripts/live_provider_smoke.py`, `scripts/vertex_smoke.py` exist but require ADC | Real extraction accuracy, redaction quality, latency, and injection resistance are unknown | Run `scripts/live_provider_smoke.py` with real ADC + synthetic text before any real use | Manual run with GCP credentials |
| F‑10 | NOT VERIFIABLE LOCALLY | — | Infra | Docker build/non-root runtime not exercised (no Docker daemon in sandbox) | `Dockerfile` reviewed statically only | Reproducibility/non-root claims unverified | Build in CI with `docker build` + `docker run --rm <img> id` to confirm non-root | CI Docker build step |
| F‑11 | CONFIRMED | Medium | Dependencies | `pip-audit` on the fully installed environment (all direct + transitive deps) found **zero known vulnerabilities** | `pip-audit -l` output | Positive finding | N/A | Re-run periodically; not a one-time check |
| F‑12 | CONFIRMED | — | DB/Migrations | Full migration cycle (`upgrade head` → `check` → `downgrade base` → `upgrade head`) succeeds cleanly against real Postgres 16 with no manual intervention | Live run, this audit | Positive finding — schema chain is sound | N/A | Reproduced above |
| F‑13 | CONFIRMED | — | Testing | 49/49 tests pass on SQLite; 45/49 pass on real Postgres+Redis (4 failures = F‑01 ×2, F‑07 ×2) | `pytest tests/ -q` under both configs | Test suite is meaningfully weaker as a real signal than "all green" suggests | See F‑06 | Reproduced above |

---

## D. End-to-End Flow Review

| Flow | Status | First failure point |
|---|---|---|
| Upload → PII scrub → storage → queue → extraction → job status | **PARTIAL** | Text uploads: works end-to-end (`main.py:286-358` → `ingestion.py:111-151`). Binary (PDF/image) uploads under `PHI_STRICT=true`: **FAIL** at PII scrubbing (`privacy.py:43-45`) — see F‑02. |
| Ingestion → persistence → timeline | **FAIL** | Fails at fact persistence the first time a fact value changes for a patient, on real Postgres — see F‑01. First upload for a brand-new fact key succeeds (no `current` row to supersede yet); the second report referencing the same fact key fails. |
| Doctor Brief / Emergency / Language generation | **PASS** (fixture/deterministic path); Vertex path **NOT VERIFIABLE LOCALLY** | Graph, disclaimer injection (`graph.py`), and structured-output validation all exercised and pass in tests. |
| SSE streaming outputs | **PARTIAL** | Happy-path streaming works in tests; no test covers client-disconnect/cancellation mid-stream. |
| Deletion (`DELETE /patients/{id}`) | **PARTIAL** | Works for patients whose facts were never superseded; fails via F‑01 for patients who have superseded facts, since the same code path is involved in setup for that test scenario. |
| Frontend (Streamlit) ↔ backend API | **PASS** (fixture path) | Frontend calls match the current async job-status polling pattern (`/reports` → `/ingestion-jobs/{id}` → `/timeline`); not independently load-tested. |
| MCP JSON-RPC surface | **PASS** | Patient-scoping enforced (`mcp_server.py:88`); covered by `tests/test_mcp.py`. |

---

## E. Concrete Patch Plan

**Priority 1 — before any pilot with real data**
- `backend/app/repositories.py`: reorder `session.add(fact)`/flush before setting `current.superseded_by` (F‑01).
- `backend/app/privacy.py` / product scope: resolve the binary-upload gap — either ship real multimodal redaction, or explicitly restrict the pilot to text uploads and update `ALLOWED_CONTENT_TYPES`/README accordingly (F‑02).
- `.github/workflows/*`: add a Postgres service container and run `pytest` against it, not only SQLite (F‑06).

**Priority 2 — before broader release**
- Add a Redis-backend test fixture that flushes Redis state between tests, and add it to CI so the Redis rate limiter and Redis metrics path have real coverage (F‑07).
- Expand `evals/synthetic_extraction_cases.json` with adversarial/prompt-injection cases and make the eval script a CI gate, not just a manual script (F‑08).
- Correct or retire the bundled `smriti-ai-production-readiness-audit_by_claude.md` findings F‑01/F‑02, which are stale against current code (F‑03/F‑04 above).

**Infrastructure / credentials (not code changes)**
- Run `scripts/live_provider_smoke.py` with real Application Default Credentials against Vertex Gemini/Gemma using only synthetic text, before any real PHI is sent (F‑09).
- Build the Docker image in CI and confirm non-root execution and reproducibility (F‑10).
- Deploy to a real Cloud Run staging service to verify multi-instance metric aggregation now that a Redis metrics backend exists, and to verify the Cloud Tasks → internal worker endpoint round-trip end-to-end.

**Organizational / clinical validation (not code)**
- Clinical review of Doctor Brief/Emergency output quality and the mandatory non-diagnostic disclaimer language.
- A compliance/legal determination (HIPAA or local equivalent) — out of scope for a code audit.

---

## F. Test Plan

```bash
# Local (SQLite, fixture path)
export DB_AUTO_CREATE=true RATE_LIMIT_BACKEND=memory SMRITI_ENV=development
pytest tests/ -q --cov=backend/app --cov-report=term-missing

# PostgreSQL (do this in CI — this audit found F-01 only by doing this)
createdb smriti_test
export DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/smriti_test"
alembic upgrade head && alembic check && alembic downgrade base && alembic upgrade head
export DB_AUTO_CREATE=false
pytest tests/ -q   # expect 0 failures once F-01 is fixed

# Redis (currently has no dedicated test coverage — add one)
export RATE_LIMIT_BACKEND=redis REDIS_URL="redis://localhost:6379/0"
redis-cli FLUSHALL  # before each test run/module
pytest tests/test_security.py -q

# Docker (NOT VERIFIABLE LOCALLY in this sandbox — no Docker daemon)
docker build -t smriti:audit .
docker run --rm smriti:audit id   # confirm non-root

# Cloud Run staging (NOT VERIFIABLE LOCALLY)
gcloud run deploy smriti-staging --source . --set-env-vars SMRITI_ENV=production,...
curl -H "Authorization: Bearer <token>" https://<staging-url>/health/ready

# Vertex Gemini / Gemma (NOT VERIFIABLE LOCALLY — needs ADC)
export GOOGLE_CLOUD_PROJECT=<project>
python scripts/live_provider_smoke.py

# Adversarial AI safety
python scripts/run_extraction_eval.py   # expand evals/synthetic_extraction_cases.json first with injection cases

# Deletion/retention
pytest tests/test_api.py -k deletion -q   # against Postgres, after F-01 fix

# Concurrency/load
python scripts/load_smoke.py --concurrency 20 --endpoint /reports
```

---

## G. Final Release Checklist

- [ ] F‑01 fixed and verified against real Postgres (fact supersession no longer throws)
- [ ] F‑02 resolved (binary uploads either work under `PHI_STRICT=true`, or product scope is explicitly text-only for this pilot)
- [ ] CI runs the full suite against Postgres, not only SQLite
- [ ] CI runs the full suite against Redis-backed rate limiting/metrics with state reset between tests
- [ ] `scripts/live_provider_smoke.py` run successfully against live Vertex Gemini + Gemma with synthetic data
- [ ] Docker image built in CI, confirmed non-root, base image pinned by digest
- [ ] Deployed to Cloud Run staging; `/health/ready`, `/metrics`, and the internal worker endpoint verified end-to-end
- [ ] Adversarial/prompt-injection eval cases added and passing
- [ ] Concurrency/load test run at expected pilot volume with p95 latency and error-rate recorded
- [ ] Deletion/retention flow re-verified against Postgres post-F‑01-fix
- [ ] Legal/compliance sign-off obtained (outside this audit's scope)
