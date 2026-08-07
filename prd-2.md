# Product Requirements Document (PRD): Smriti AI Health Memory

## 1. Executive Summary
Smriti AI is a patient-centric, longitudinal health memory system designed to consolidate fragmented medical data into a structured, immutable timeline. By leveraging an agentic mesh architecture, Smriti extracts clinical facts from uploaded reports, preserves historical context through an append-only versioning model, and generates on-demand, real-time summaries for patients, clinicians, and emergency responders. The system prioritizes privacy through local PII scrubbing and confidential computing roadmaps.

## 2. Problem Statement
Patients and caregivers struggle with fragmented medical records spread across multiple providers. Critical information—such as allergies, chronic conditions, and medication history—is often lost, misreported, or overwritten in electronic health records (EHRs). There is a lack of a "single source of truth" that is owned by the patient, preserves historical changes, and can provide immediate, simplified context during clinical visits or emergencies.

## 3. Goals & Objectives
*   **Cumulative Memory:** Build a persistent, longitudinal health profile that grows with every report.
*   **History Preservation:** Implement an append-only data model where facts are superseded rather than deleted.
*   **Contradiction Awareness:** Automatically identify and flag conflicting medical information for human review.
*   **Actionable Outputs:** Provide high-utility summaries (Doctor Briefs, Emergency Cards) via low-latency streaming.
*   **Privacy-First Design:** Ensure data isolation and PII protection before cloud processing.
*   **Interoperability:** Use standardized protocols (MCP) to allow the health memory to serve as a context provider for other AI tools.

## 4. Target Users / Stakeholders
*   **Patients:** Primary owners who upload reports and manage their health timeline.
*   **Caregivers:** Authorized users managing health data for family members.
*   **Clinicians:** Consumers of the "Doctor Brief" to quickly catch up on patient history.
*   **Emergency Responders:** Consumers of the "Emergency Card" for life-saving data (allergies, blood type).

## 5. Functional Requirements
### 5.1 Report Ingestion & Extraction
*   **Multi-format Support:** Support PDF, image, and text-based medical report uploads.
*   **PII Scrubbing:** Local scrubbing of Personal Identifiable Information using Gemma 2B/7B before cloud transmission.
*   **Structured Extraction:** Extract clinical entities (medications, labs, conditions) using Gemini 3.1 Pro.
*   **Explanation:** Provide a plain-language explanation of the extracted data to the user.

### 5.2 Health Memory Management
*   **Append-Only Facts:** Every fact must have a `superseded_by` pointer to maintain a full audit trail.
*   **Contradiction Engine:** Detect discrepancies between new reports and existing memory (e.g., conflicting blood types or medication dosages).
*   **Timeline Visualization:** Display a chronological view of health events and fact evolutions.

### 5.3 On-Demand Agentic Outputs
*   **Doctor Brief:** A clinical summary optimized for physician review (Gemini 3.5 Flash).
*   **Emergency Card:** A high-priority summary of allergies, critical conditions, and emergency contacts.
*   **Translation:** Real-time translation of health data into regional languages (e.g., Hindi).
*   **Streaming Responses:** Support for Server-Sent Events (SSE) for all on-demand summaries to improve perceived latency.

### 5.4 Context Gateway
*   **MCP Integration:** Provide a Model Context Protocol (MCP) interface for external tools to query the health memory securely.

## 6. Non-Functional Requirements
*   **Security:** Mandatory OAuth2/OIDC for production; fail-closed authorization.
*   **Performance:** SSE streaming for agent responses; API response times for ingestion < 10s (excluding LLM latency).
*   **Reliability:** PostgreSQL as the source of truth with Alembic for schema migrations.
*   **Scalability:** Stateless FastAPI workers; Redis-backed rate limiting.
*   **Observability:** Full OpenTelemetry (OTel) integration for tracing agentic workflows and token usage.

## 7. System Architecture Overview
The system is divided into five logical layers:
1.  **Edge & Security Layer:** Streamlit UI and FastAPI Gateway handling authentication and orchestration.
2.  **Privacy Enclave:** Local Gemma-based PII scrubbing plus an Antigravity confidential-computing integration boundary.
3.  **Agent Mesh:** A LangGraph-powered network of specialized agents (Understanding, Memory, Brief, Emergency, Language).
4.  **Data Persistence Layer:** PostgreSQL for relational facts, a Vector Search integration boundary for semantic history, and BigQuery for anonymized analytics.
5.  **Observability Stack:** Centralized OTel tracing and logging.

## 8. Tech Stack
*   **Frontend:** Streamlit, Python
*   **Backend API:** FastAPI, LangGraph, SQLModel
*   **AI/ML:** Gemini 3.1 Pro, Gemini 3.5 Flash/Lite, Gemma 2B/7B (Local)
*   **Database:** PostgreSQL (Cloud SQL), Vector Search adapter with pgvector-compatible fallback
*   **Protocols:** MCP (Model Context Protocol), SSE (Server-Sent Events), OAuth2/OIDC
*   **Infrastructure:** Docker, Cloud Run deployment manifests, Google Cloud Storage
*   **Monitoring:** OpenTelemetry, Cloud Trace, BigQuery (Audit)

## 9. Data Requirements
*   **Relational Schema:**
    *   `patients`: Identity and metadata.
    *   `reports`: Raw source data and extraction logs.
    *   `health_facts`: Typed clinical data with `superseded_by` logic and `is_emergency` flags.
    *   `contradictions`: Links between conflicting facts for manual resolution.
*   **Data Flow:** Raw Report -> PII Scrubber -> Extraction Agent -> Memory Agent -> Postgres -> On-demand Agents -> UI.

## 10. API Specifications
*   `POST /reports`: Upload and trigger extraction.
*   `GET /timeline`: Retrieve the longitudinal health record.
*   `POST /brief/stream`: SSE endpoint for clinical summaries.
*   `POST /emergency/stream`: SSE endpoint for emergency cards.
*   `POST /translate/stream`: SSE endpoint for multi-language support.
*   `POST /mcp`: JSON-RPC endpoint for context retrieval.
*   `POST /contradictions/{id}/review`: Authorized HITL review decision.

## 11. Security Requirements
*   **Identity:** OIDC JWT validation (Issuer, Audience, Expiry).
*   **Isolation:** Patient-level data partitioning in PostgreSQL.
*   **Privacy:** Gemma-based scrubbing ensures no raw PII reaches cloud LLMs unless explicitly authorized.
*   **Encryption:** AES-256/Fernet encryption at rest for local uploads; provider-managed or customer-managed encryption for GCS/PostgreSQL; TLS 1.3 for external transport where supported.
*   **Retention:** Configurable report retention with an explicit deletion workflow and audit event; append-only clinical facts remain subject to legal/clinical retention policy.
*   **Compliance:** GDPR-style access, correction, deletion, data minimization, and audit controls are required before handling real production patient data.
*   **API security:** OWASP API Security Top 10 controls, request size/type validation, patient ownership checks, rate limiting, and fail-closed provider errors.
*   **Audit:** State transitions, access decisions, provider calls, and LLM metadata are logged without report contents; BigQuery delivery is opt-in and environment-configured.

## 12. Deployment & Infrastructure
*   **Local:** Docker Compose with PostgreSQL and Redis.
*   **Production:** Cloud Run deployment manifests are provided for the API/frontend boundary; Cloud SQL is the target PostgreSQL service. Live deployment requires project credentials, secrets, billing, and operational approval.
*   **CI/CD:** Automated migrations via Alembic; OTel instrumentation for all environments.

## 13. Success Metrics
*   **Extraction Accuracy:** % of clinical facts correctly identified vs. ground truth.
*   **User Retention:** Frequency of report uploads and timeline views.
*   **Latency:** Time to first token for SSE streaming outputs.
*   **Safety:** Zero instances of PII leakage in cloud logs.

## 14. Timeline & Milestones
*   **Phase 1 (MVP):** Local ingestion, Postgres persistence, and basic Streamlit UI.
*   **Phase 2 (Cloud):** FastAPI Gateway, OIDC integration, and Cloud Run deployment.
*   **Phase 3 (Agent Mesh):** SSE streaming for Brief/Emergency agents and MCP Gateway.
*   **Phase 4 (Advanced Privacy):** Harden Gemma model serving, configure Antigravity confidential-state adapter, and complete compliance evidence.

## 15. Open Questions & Risks
*   **Vertex AI Billing:** System requires active billing for Gemini 3.1 Pro extraction.
*   **Legal Disclaimer:** Smriti is not a diagnostic tool; UI must clearly state this to mitigate liability.
*   **A2A Protocol:** The A2A boundary is specified as an interoperability contract; runtime agent exchange remains gated on the selected protocol version and deployment environment.

## 16. Requirement IDs and acceptance criteria

| ID | Requirement | Acceptance criteria | Evidence |
|---|---|---|---|
| FR-01 | Accept medical reports | PDF, PNG/JPEG, and TXT uploads; maximum 10 MB; extension, MIME, and optional signature validation | `backend/app/main.py`, `tests/test_api.py` |
| FR-02 | Scrub report PII before cloud processing | Scrubber runs before the Vertex extraction boundary; strict production mode rejects unsupported binary scrubbing | `backend/app/privacy.py`, `backend/app/graph.py`, `tests/test_providers.py` |
| FR-03 | Preserve append-only history | Changed values create a new fact and link the prior fact through `superseded_by`; current facts are unique per patient/key | `backend/app/repositories.py`, Alembic migration, `tests/test_memory.py` |
| FR-04 | Detect contradictions | Conflicting values create an unresolved contradiction record and surface it in the timeline | `backend/app/models.py`, `backend/app/repositories.py`, `tests/test_memory.py` |
| FR-05 | Generate on-demand outputs | Doctor Brief, Emergency, and Language endpoints read current memory without mutating facts | `backend/app/graph.py`, `backend/app/main.py` |
| FR-06 | Stream outputs | `/brief/stream`, `/emergency/stream`, and `/translate/stream` emit SSE chunks and a terminal event | `backend/app/main.py`, `frontend/streamlit_app.py` |
| FR-07 | Secure context access | MCP tools validate UUIDs and enforce OIDC patient ownership before database access | `backend/app/mcp_server.py`, `tests/test_mcp.py` |
| FR-08 | Human contradiction review | Authorized users can inspect an unresolved contradiction and record `confirm_older`, `confirm_newer`, or `leave_unresolved` without deleting facts | `POST /contradictions/{id}/review`, `backend/app/repositories.py`, API tests |
| NFR-01 | Patient isolation | Cross-patient access returns 403; production requests require OIDC or an explicitly configured service token | `backend/app/security.py`, `tests/test_security.py` |
| NFR-02 | Reliability | PostgreSQL migrations pass upgrade/downgrade/reapply; Redis is the production rate-limit backend | `.github/workflows/ci.yml`, `infra/alembic/` |
| NFR-03 | Privacy and retention | Production local storage requires an encryption key; retention cleanup and deletion are tested; audit logs exclude report contents | `backend/app/storage.py`, `tests/test_storage.py` |
| NFR-04 | Performance | Upload payload is limited to 10 MB; ingestion target is under 10 seconds excluding LLM latency; SSE time-to-first-token is measured in deployment tests | API validation and deployment test plan |
| NFR-05 | Observability | Requests carry correlation IDs; OTel and anonymized audit sinks are configurable without code changes | `backend/app/observability.py`, `backend/app/main.py` |

## 17. Compliance and data lifecycle

Smriti uses data minimization by default: report contents are not written to
logs or analytics events. Uploaded source objects are encrypted when local
storage is used in production and can be deleted through the storage boundary.
Retention is configured with `STORAGE_RETENTION_DAYS`; production deployments
must define a non-zero policy and document legal or clinical exceptions.

The deletion workflow is separate from the append-only clinical ledger.
Deleting a source report removes the binary object and its retrievable
reference. Clinical facts remain immutable until a governed retention or legal
erasure process authorizes removal, with the action recorded as an audit event.
Real patient data must not be used until data-controller, processor, consent,
access, correction, and erasure policies are approved for the deployment.

## 18. CRISPE prompt contracts

All agent prompts use the CRISPE structure: **Context**, **Role**,
**Instruction**, **Specifics**, **Performance criteria**, and **Examples**.
Prompts are versioned through the local or AI Studio prompt registry.

### `extract.v1` — Report Understanding Agent

- Context: a patient-provided report after PII scrubbing.
- Role: faithful clinical-information extraction assistant.
- Instruction: extract only explicitly recorded facts; never diagnose or infer.
- Specifics: return schema-valid JSON with type, key, value, date, status,
  emergency relevance, and confidence.
- Performance: unsupported facts are forbidden; invalid JSON is rejected.
- Examples: positive, empty-report, and ambiguous-date cases.

### `memory.v1` — Memory Agent

- Context: validated extracted facts and current patient memory.
- Role: append-only memory steward.
- Instruction: insert new facts, supersede changed values, and record
  contradictions without silently resolving them.
- Specifics: preserve report provenance and patient ownership.
- Performance: no destructive overwrite; transaction is atomic.
- Examples: unchanged, changed, and conflicting fact cases.

### `brief.v1` — Doctor Brief Agent

- Context: current facts plus unresolved contradictions.
- Role: clinician-facing summarizer.
- Instruction: organize recorded information and call out uncertainty.
- Specifics: do not diagnose, prescribe, or invent missing history.
- Performance: concise, source-grounded, and deterministic when provider is off.
- Examples: empty memory and contradiction-heavy memory.

### `emergency.v1` — Emergency Agent

- Context: current emergency-relevant facts only.
- Role: emergency information formatter.
- Instruction: present allergies, critical conditions, and medications clearly.
- Specifics: never claim emergency dispatch or treatment authority.
- Performance: omit unverified facts and preserve source wording.
- Examples: no emergency facts and multiple allergy facts.

### `language.v1` — Language Agent

- Context: current patient-owned facts and target language.
- Role: faithful health-information translator.
- Instruction: translate without changing facts, certainty, or safety caveats.
- Specifics: use plain language and preserve medical names where needed.
- Performance: no added advice or diagnosis.
- Examples: English-to-Hindi and English-to-Kannada summaries.

## 19. Human-in-the-loop contradiction flow

1. Memory Agent detects a conflicting fact and stores an unresolved contradiction.
2. Timeline and Doctor Brief surface the contradiction with both fact versions.
3. An authorized patient, caregiver, or clinician reviews the source reports.
4. The reviewer records a decision or leaves the contradiction unresolved.
5. The ledger remains append-only; review metadata never rewrites historical facts.

The reviewer role, consent scope, and final resolution policy must be selected
per deployment before clinician sharing is enabled.

## 20. Mandatory stack integration boundaries

The submission treats the required hackathon components as explicit integration
boundaries rather than claiming that paid cloud execution has already occurred:

- **AI Studio:** versioned prompt registry adapter.
- **Gemini:** Vertex extraction and generation adapters with deterministic fallback.
- **Gemma:** local and strict PII scrubber boundary before cloud provider calls.
- **Antigravity:** secure-state adapter boundary; runtime requires the approved SDK/environment.
- **ADK:** optional tool registration and agent-tool contracts.
- **MCP:** secured context gateway for patient-authorized retrieval.
- **A2A:** versioned agent-to-agent contract boundary; runtime exchange is environment-gated.
- **Vertex AI:** extraction/generation and future vector-retrieval provider boundaries.
- **Cloud Run:** deployable service manifests for API/frontend separation; live rollout is environment-gated.
- **BigQuery:** anonymized audit and analytics sink boundary.

---

# Expert Review & Feedback

### Strengths
1.  **Append-Only Model:** The `superseded_by` logic is a masterstroke for medical data. It treats health history like a git commit log, which is essential for clinical safety and auditing.
2.  **Privacy Layering:** Using Gemma locally for PII scrubbing before hitting Gemini Pro addresses the #1 concern in healthcare AI: data privacy.
3.  **Architectural Decoupling:** Separating the "Ingestion" path from the "On-demand" path prevents the system from becoming a bottleneck and allows for independent scaling of agents.
4.  **Interoperability:** Including the MCP (Model Context Protocol) gateway positions Smriti not just as an app, but as a platform/infrastructure component.

### Areas for Improvement / Risks
1.  **Contradiction Resolution:** The PRD mentions flagging contradictions, but the "Human-in-the-loop" (HITL) workflow for resolving them is not fully defined. Who has the final say—the patient or a future doctor?
2.  **Vector Search Cost:** Vertex AI Vector Search can be expensive for small patient cohorts. Consider starting with pgvector (Postgres) before moving to a dedicated vector database.
3.  **Cold Starts:** Using Cloud Run for LLM-heavy agents might lead to cold-start latency. Ensure the FastAPI gateway has aggressive "warm-up" or "min-instances" configured for the SSE routes.

### Final Verdict
This is a **production-ready architecture**. The transition from a "prototype" to a "longitudinal memory system" is well-supported by the choice of LangGraph and the structured data model. Proceed to Phase 2 (Cloud Integration).
