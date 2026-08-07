# SMRITI.AI Security & Codebase Audit Report (historical)

> This report is retained as audit history. It is superseded by the repository
> implementation and the current audit delivered on 2026-08-07. In particular,
> the MCP authorization, CI hardening, current-fact uniqueness, and MIME
> validation findings below have since been addressed.

## Executive Summary
**SMRITI.AI** has a clean prototype structure (`FastAPI` backend, `Streamlit` UI, `SQLModel` schema, `LangGraph` orchestration, tests), but it has **one critical authorization flaw** and several high-impact security/operational gaps before production use.

* **Most Important**: The `/mcp` endpoint can access arbitrary patient IDs even in OIDC mode.
* **Key Risks**: PHI handling (PII bypass on non-text uploads), CI/security hardening, dependency reproducibility, and reliability/performance under real load.

---

## Architecture & Structure Map

* **Backend API / Orchestration**: `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app`
  * `main.py`: FastAPI routes, middleware
  * `graph.py`: Ingestion/output LangGraph nodes
  * `repositories.py`, `models.py`, `db.py`: Persistence layer
  * `security.py`: Auth + rate limit
  * `extractor.py`, `generation.py`, `privacy.py`: Provider boundaries
  * `mcp_server.py`, `adk_tools.py`, `integrations.py`: MCP/ADK/integration adapters
* **Frontend**: `/home/runner/work/SMRITI.AI/SMRITI.AI/frontend/streamlit_app.py`
* **DB Schema / Migrations**: `/home/runner/work/SMRITI.AI/SMRITI.AI/infra`
* **CI/CD**: `/home/runner/work/SMRITI.AI/SMRITI.AI/.github/workflows/ci.yml`
* **Tests**: `/home/runner/work/SMRITI.AI/SMRITI.AI/tests`

---

## Full Findings

### 1. Critical — Authorization bypass on MCP tools (Cross-patient data access)
* **Category**: Security / AuthZ
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/mcp_server.py:60-96` (uses `params["arguments"]["patient_id"]` directly)
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/main.py:64-72` (other API paths enforce patient binding via `resolve_patient_id`)
* **Why it matters**: In OIDC mode, a user can call `/mcp` with another patient’s UUID and read their facts/contradictions.
* **Fix**: Pass `Request` into MCP handler and enforce same patient binding logic as `resolve_patient_id` before tool execution.

### 2. High — Non-text uploads bypass PII scrubbing
* **Category**: Security / Privacy
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/privacy.py:31-32`
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/privacy.py:91-93`
* **Why it matters**: PDFs/images likely contain PHI and are passed through unsanitized.
* **Fix**: Add explicit policy: either block non-text in strict mode or run a proper multimodal redaction step before extraction/provider calls.

### 3. High — CI security hardening gaps (Permissions + Pinning)
* **Category**: CI/CD Security
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/.github/workflows/ci.yml:12,13` uses tag-based actions (`@v4`, `@v5`), not commit SHAs.
  * No explicit `permissions:` block in workflow.
* **Why it matters**: Broader token scope than needed + mutable action tags increase supply-chain risk.
* **Fix**: Add least-privilege permissions and pin actions to immutable SHAs.

### 4. High — Missing automated security gates in CI
* **Category**: Security / Quality Gates
* **Evidence**: `/home/runner/work/SMRITI.AI/SMRITI.AI/.github/workflows/ci.yml:16-21` only runs install, `pip check`, and `pytest`.
* **Why it matters**: No secret scanning, SAST, or dependency vulnerability checks in PR gate.
* **Fix**: Add at minimum: dependency audit (`pip-audit`), secret scan, and CodeQL/Bandit static analysis.

### 5. High — No lockfile / Deterministic dependency resolution
* **Category**: Dependencies / Supply Chain
* **Evidence**:
  * `pyproject.toml` uses ranges (`>=`, `<`).
  * No lockfile present at repo root (`poetry.lock`, `uv.lock`, etc.).
* **Why it matters**: Non-reproducible builds and drifting transitive dependency risk.
* **Fix**: Adopt lockfile strategy (e.g., `pip-tools`, `uv`, or `poetry.lock`) and enforce in CI.

### 6. Medium — Shared default patient fallback can mix data if `patient_id` omitted
* **Category**: Security / Multi-tenancy
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/main.py:35`
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/main.py:72`
* **Why it matters**: Missing `patient_id` can map writes/reads to a global UUID in non-OIDC flows.
* **Fix**: Require `patient_id` unless OIDC claim is present; remove global fallback in non-dev modes.

### 7. Medium — Potential race condition for “current fact” uniqueness
* **Category**: Data Integrity / Reliability
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/models.py:39` partial index is not unique.
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/repositories.py:53-80` read-then-write merge logic.
* **Why it matters**: Concurrent ingests may produce multiple current rows for same `(patient_id, fact_key)`.
* **Fix**: Use unique partial index (`UNIQUE WHERE superseded_by IS NULL`) + retry on conflict / transaction-level protection.

### 8. Medium — Rate limiter keying on client host only
* **Category**: Security / Reliability
* **Evidence**: `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/security.py:110`
* **Why it matters**: NAT/proxy users share quota; spoofing/proxy behavior can distort limits.
* **Fix**: Use authenticated subject/patient ID when available; add trusted proxy handling strategy.

### 9. Medium — Upload type validation is permissive (“MIME OR extension”)
* **Category**: Security / Input Validation
* **Evidence**: `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/main.py:80`
* **Why it matters**: Crafted files can pass if either field looks valid.
* **Fix**: Require both extension and MIME match allowlist; optionally add magic-byte sniffing.

### 10. Medium — Audit sink initialization on every audit event
* **Category**: Performance / Reliability
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/observability.py:40-43`
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/integrations.py:150-158`
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/integrations.py:131-137`
* **Why it matters**: Repeated client creation adds latency and failure surface on hot paths.
* **Fix**: Cache sink/client singleton; make writes async/buffered where possible.

### 11. Medium — Local report storage is plaintext and persistent by default
* **Category**: Security / Ops
* **Evidence**: `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/storage.py:25-27`
* **Why it matters**: PHI exposure risk on local disks/dev environments.
* **Fix**: Add retention + encryption guidance; support optional encryption-at-rest for local mode.

### 12. Medium — External integration calls lack retry/backoff strategy
* **Category**: Reliability
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/extractor.py:162-166`
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/generation.py:59-63`
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/integrations.py:68`
* **Why it matters**: Transient provider/network failures surface directly as user-visible errors.
* **Fix**: Add bounded retries with jitter for transient classes; preserve fast-fail for permanent errors.

### 13. Medium — No lint/type-check enforcement in repository or CI
* **Category**: Code Quality / Quality Gates
* **Evidence**: `pyproject.toml` contains `pytest` config only; no `ruff`/`black`/`mypy` config. `.github/workflows/ci.yml` runs tests only.
* **Why it matters**: Style/type regressions and latent bugs can pass CI.
* **Fix**: Add and enforce linter + type checker in CI.

### 14. Medium — CI does not validate migrations against Postgres
* **Category**: CI/CD / Reliability
* **Evidence**: `.github/workflows/ci.yml` has no Postgres service or Alembic upgrade job.
* **Why it matters**: Migration/runtime drift can break deployments despite green CI.
* **Fix**: Add migration smoke job (upgrade head, optionally downgrade/upgrade cycle).

### 15. Low — Duplicate test logic across files
* **Category**: Maintainability / Tests
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/tests/test_mcp.py:8-40`
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/tests/test_integrations.py:8-35` (near-duplicate MCP behavior checks)
* **Why it matters**: Duplicate tests increase maintenance cost and drift risk.
* **Fix**: Consolidate MCP endpoint tests in one file/module.

### 16. Low — File naming/content mismatch in infra migrations folder
* **Category**: Documentation / DevEx
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/infra/migrations/README.md:1-3` contains SQL include.
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/infra/migrations/001_initial_schema.sql:1-14` contains README prose.
* **Why it matters**: Onboarding confusion and operational mistakes.
* **Fix**: Swap/rename content to match filenames.

### 17. Low — Dead/unused compatibility helper
* **Category**: Code Quality
* **Evidence**: `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/extractor.py:199-207` (`extract_report()`) has no references.
* **Why it matters**: Increases API surface and maintenance burden.
* **Fix**: Remove or mark deprecated with explicit consumers.

### 18. Low — Unused import in MCP server
* **Category**: Code Quality
* **Evidence**: `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/mcp_server.py:12` imports `Session` but unused.
* **Why it matters**: Minor cleanliness issue.
* **Fix**: Remove unused import; enforce linting.

### 19. Low — Middleware doesn’t guarantee request audit/header on unhandled exceptions
* **Category**: Observability / Reliability
* **Evidence**: `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/main.py:51-61` sets headers/logs only after successful `call_next`.
* **Why it matters**: Failed requests may miss traceability.
* **Fix**: Wrap `call_next` in `try/finally` and emit failure audit with status class.

### 20. Low — Frontend/backend communication has fixed timeout and no retry
* **Category**: UX / Reliability
* **Evidence**: `/home/runner/work/SMRITI.AI/SMRITI.AI/frontend/streamlit_app.py:26`
* **Why it matters**: Temporary backend slowness yields immediate UX errors.
* **Fix**: Add configurable timeout + one safe retry for idempotent GETs.

### 21. Low — README setup is PowerShell-centric
* **Category**: DevEx / Documentation
* **Evidence**: `/home/runner/work/SMRITI.AI/SMRITI.AI/README.md:30-38,44-47,110-113,124-125`
* **Why it matters**: Linux/macOS onboarding friction.
* **Fix**: Add Bash equivalents.

### 22. Info — Optional integrations are clearly isolated behind provider boundaries
* **Category**: Architecture Strength
* **Evidence**: `extractor.py`, `generation.py`, `privacy.py`, `integrations.py`
* **Why it matters**: Good separation for testability and phased rollout.
* **Fix**: Keep this pattern; add stronger interface contracts over time.

### 23. Info — Append-only fact model + contradiction table is a strong longitudinal design
* **Category**: Architecture Strength
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/models.py:36-66`
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/backend/app/repositories.py:79-92`
* **Why it matters**: Good auditability and temporal trace.
* **Fix**: Add concurrency guardrails and integrity constraints.

### 24. Info — Docs contain intentional roadmap-vs-current behavior split but with drift risk
* **Category**: Documentation
* **Evidence**:
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/README.md:138-141` (streaming listed as roadmap)
  * `/home/runner/work/SMRITI.AI/SMRITI.AI/Smriti_Project_Context.md:149` (states outputs “should stream”)
* **Why it matters**: Can confuse contributors on what is current vs. target.
* **Fix**: Add explicit “Current state” vs “Target state” sections consistently in all docs.

---

## Prioritized Remediation Plan

### Immediate (0–7 days)
1. Fix MCP authorization bypass (**Critical**).
2. Add CI hardening: pinned SHAs + least-privilege workflow permissions.
3. Add baseline security gates (secret scan + dependency vuln scan + static security scan).
4. Enforce `patient_id` requirements / remove unsafe default fallback outside local dev.
5. Correct infra migration file naming/content mismatch.

### Short Term (1–4 weeks)
1. Add unique partial constraint / transactional conflict handling for current facts.
2. Strengthen upload validation (MIME + extension + optional signature sniffing).
3. Implement strict PHI handling policy for non-text uploads.
4. Add migration CI job against Postgres.
5. Add lint/type-check jobs and remove dead/duplicate code/tests.

### Medium Term (1–3 months)
1. Introduce retry/backoff policies and resilience patterns for all external providers.
2. Refactor audit sink/client lifecycle for cached/async delivery.
3. Add storage encryption/retention controls for local and cloud modes.
4. Expand observability (error budgets, structured failure metrics, alerting).
5. Align all docs and runbooks for deployment and incident response readiness.

---

## Quick-Win Patch Suggestions (Optional)
* **MCP patient binding fix** — *Effort: S, Risk: Low-Med*
* **Workflow permissions + action SHA pinning** — *Effort: S, Risk: Low*
* **Add `pip-audit` + secret scan in CI** — *Effort: S, Risk: Low*
* **Swap misnamed migration docs/files** — *Effort: XS, Risk: Low*
* **Remove unused import/dead helper + dedupe MCP tests** — *Effort: XS-S, Risk: Low*
