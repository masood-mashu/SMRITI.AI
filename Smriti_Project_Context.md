# Smriti — AI Health Memory Agent

**Tagline:** Never repeat your medical history again.

**Context:** Built for the AI Agent Builder Series 2026 Grand Finale (Top 100 AI Builders in India), a 12-hour in-person hackathon at the Google Kyoto Office, Bengaluru, on Aug 8, 2026. Track: HealthTech — "Repeated Medical History," combined with "Medical Report Simplification" as the product's entry point. Build starts now, days ahead of the final; the 12 hours on-site are for polish, integration, and demo rehearsal, not the whole build.

This document is written to be handed to any AI coding assistant (Codex, Copilot, etc.) as full project context before asking it to write code. Read this fully before generating anything.

---

## 1. The problem

Patients repeatedly explain the same medical history across different hospitals and clinics. There's no patient-owned system that remembers, organizes, and instantly surfaces a person's health history — allergies, medications, past reports, chronic conditions — across visits. Existing tools either summarize a single document or offer a generic chatbot; neither solves the recurring, cumulative nature of the problem.

## 2. The product vision

Smriti is a personal AI Health Memory Agent that the patient owns and feeds over time by uploading their own reports (photos, PDFs, scans — no hospital integration required, no interoperability claims). Every report is understood, extracted, and merged into a structured, growing health profile with full history. That memory then powers multiple outputs on demand: a doctor-ready clinical brief, an emergency profile, a plain-language explanation, and translations into regional languages.

It should feel like a personal AI operating system for health — not a single-purpose document summarizer, and explicitly not a diagnostic tool.

## 3. Users

- **Primary:** patients and caregivers managing an ongoing relationship with the healthcare system — chronic conditions, multiple specialists, elderly family members.
- **Secondary (demo-relevant):** a doctor receiving a generated brief; an emergency responder needing a critical-info card fast.

## 4. Agent architecture

Five agents, each with one clear responsibility, orchestrated as a stateful graph:

1. **Report Understanding Agent** — ingests a photo/PDF/scan of a medical report. Uses Gemini 3.1 Pro's native multimodal capability directly (no separate OCR library — raw file bytes go straight to Gemini) to extract structured medical facts (conditions, medications, allergies, lab values, dates). Streams a plain-language explanation back to the UI live as it processes — this is the opening beat of the demo.
2. **Memory Agent** — the core of the system. Owns the patient's structured, longitudinal health profile (see schema below). Merges each new extraction into existing memory using an append-only, fully-historied pattern — nothing is ever overwritten, so a real timeline and contradiction-detection are both possible. Fans out to the three downstream agents on demand.
3. **Doctor Brief Agent** — reads current memory state, generates a concise clinical summary, and flags contradictions across the patient's history (e.g. a medication that was later discontinued, or a value trending in a concerning direction). Uses vector search over past report content for this.
4. **Emergency Agent** — generates a one-tap critical-info card (allergies, chronic conditions, current medications, emergency contact) from a fast structured lookup against the memory store. No heavy reasoning needed — the "emergency relevant" flag is set once at extraction time.
5. **Language Agent** — translates any output into plain, non-medical language and into regional languages, starting with Kannada and Hindi.

**Data flow:** User uploads a report → Report Understanding Agent extracts + streams an explanation → Memory Agent merges the extraction into history → Memory Agent fans out to Doctor Brief / Emergency / Language agents on request → each streams its output back to the UI.

## 5. Tech stack (with rationale)

- **LLM:** Gemini 3.1 Pro (Report Understanding — needs strong multimodal reasoning), Gemini 3.5 Flash (Doctor Brief, Language), Gemini 3.5 Flash-Lite (Emergency — fast, low-reasoning card generation). Use the **Vertex AI SDK** (`google-cloud-aiplatform`), not the AI Studio SDK — better rate limits and GCP credit integration for hackathon participants.
- **Orchestration:** LangGraph — chosen over Google ADK because it's purpose-built for the stateful-graph pattern the Memory Agent needs (explicit state passing between agents, support for cycles if an agent needs to request clarification).
- **Backend:** FastAPI, orchestrating the LangGraph workflow and serving the API.
- **Frontend:** Streamlit — patient-facing interface for upload, timeline view, and streamed outputs.
- **Structured storage:** Postgres (Cloud SQL) with SQLModel — the source of truth for the health profile. Chosen over a NoSQL/Firestore approach because contradiction-detection and timeline queries are naturally relational.
- **Vector store:** Vertex AI Vector Search, used for semantic search over report history (Doctor Brief Agent's contradiction-checking). Development note: Qdrant is fine for early local iteration since it's faster to stand up; migrate to Vertex AI Vector Search once the pipeline is stable, ahead of the final — not live during the 12 hours.
- **Deployment:** Cloud Run for the full application layer (Streamlit + FastAPI + agents), with CI/CD set up during prep days so every push auto-deploys to a stable demo URL.
- **Streaming:** all four output agents (Report Understanding, Doctor Brief, Emergency, Language) stream their responses live to the UI rather than returning a single completed block — this is a deliberate demo-quality decision, not just a technical nicety.

## 6. Data schema

Append-only, fully-historied design — nothing is overwritten, "current state" is just the row with no successor.

```sql
CREATE TABLE patients (
    patient_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reports (
    report_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     UUID NOT NULL REFERENCES patients(patient_id),
    source_type    TEXT NOT NULL,        -- 'lab_result' | 'discharge_summary' | 'prescription' | 'other'
    uploaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    file_url       TEXT,
    raw_extraction JSONB
);

CREATE TABLE health_facts (
    fact_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id             UUID NOT NULL REFERENCES patients(patient_id),
    report_id              UUID REFERENCES reports(report_id),
    fact_type              TEXT NOT NULL,   -- 'condition' | 'medication' | 'allergy' | 'lab_value' | 'procedure' | 'vaccination'
    fact_key               TEXT NOT NULL,   -- normalized name, e.g. 'HbA1c', 'Metformin'
    fact_value              TEXT NOT NULL,
    unit                    TEXT,
    status                  TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'resolved' | 'discontinued'
    is_emergency_relevant   BOOLEAN NOT NULL DEFAULT false,
    effective_date          DATE NOT NULL,
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_by           UUID REFERENCES health_facts(fact_id),  -- NULL = current value
    confidence              REAL
);

CREATE INDEX idx_facts_current ON health_facts (patient_id, fact_key) WHERE superseded_by IS NULL;
CREATE INDEX idx_facts_timeline ON health_facts (patient_id, effective_date);

CREATE TABLE contradictions (
    contradiction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id       UUID NOT NULL REFERENCES patients(patient_id),
    fact_id_older    UUID NOT NULL REFERENCES health_facts(fact_id),
    fact_id_newer    UUID NOT NULL REFERENCES health_facts(fact_id),
    description      TEXT NOT NULL,
    detected_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved         BOOLEAN NOT NULL DEFAULT false
);
```

**Query patterns per agent:** Report Understanding inserts into `reports` + `health_facts`. Memory Agent's "merge" is just: look up the current row for `patient_id + fact_key`; if the new value differs, set the old row's `superseded_by`. Doctor Brief reads current facts plus walks `superseded_by` chains to detect contradictions. Emergency Agent does a single filtered query on `is_emergency_relevant`. Timeline view is `ORDER BY effective_date`, grouped by `fact_key`.

## 7. Differentiation from typical hackathon submissions

Most competing teams will build either a records-storage app or a single-document Q&A chatbot. Smriti differentiates by:
- Genuine agentic reasoning — flagging contradictions and generating proactive summaries, not just answering questions.
- A true multi-agent pipeline, each agent with a distinct responsibility, coordinated around one shared memory layer.
- Full historical memory (not just "latest state"), enabling a real timeline and trend detection.
- Regional language output — a small addition most teams won't bother with, high relevance to the Indian judging context.

## 8. Explicitly out of scope

- Real hospital/EHR integration or interoperability claims — the patient uploads their own documents; there is no claim of pulling records from institutions.
- Production-grade multi-user auth, HIPAA-grade compliance — acknowledged as future work only.
- Any diagnosis or treatment recommendation, in any agent, under any framing. Smriti explains and organizes; it never diagnoses.

## 9. Demo script

1. Judge uploads (or hands over) a real report live.
2. Report Understanding Agent extracts and streams a plain-language explanation.
3. The extraction is merged into memory; timeline updates.
4. Judge asks: "What allergies do I have?" → instant answer from memory.
5. Judge asks: "Generate a summary for my cardiologist." → Doctor Brief Agent streams a response.
6. Judge asks: "Generate an emergency card." → Emergency Agent responds fast.
7. Judge asks: "Explain this in Kannada." → Language Agent streams a translated response.

## 10. Build plan

**Pre-hackathon (before Aug 8):**
- Core: report upload, Gemini-native extraction, Postgres schema, Memory Agent merge logic, timeline view.
- Agents: Doctor Brief, Emergency, Language — each wired to Memory Agent and streaming to the UI.
- Vector search: prototype on Qdrant locally first; migrate to Vertex AI Vector Search once stable.
- Cloud Run deployment with CI/CD so every push updates the live demo URL.
- Seed a realistic demo profile (3–5 reports across a plausible timeline) so the "memory" story doesn't depend on fabricating history live on stage.

**12-hour final (Aug 8):**
- Polish UI, harden the live-upload path (must not fail on stage), rehearse the full demo script end-to-end at least twice, prepare a clean pre-loaded sample report as backup in case live OCR/extraction misbehaves on an unfamiliar document.

## 11. Key risks and mitigations

| Risk | Mitigation |
|---|---|
| Live extraction fails on an unfamiliar document on stage | Always have a clean pre-loaded sample ready as backup alongside the live upload |
| Judges question data privacy/liability | Frame explicitly as patient-owned, patient-controlled memory — never a diagnostic tool |
| Too many agents dilute the pitch | Hold firmly to 5 agents, each explainable in one sentence |
| Multi-agent coordination bugs under time pressure | Rehearse the full demo script end-to-end multiple times before the final |

## 12. Notes for AI coding assistants picking this up

- Match the schema exactly as given above — the merge logic, contradiction detection, and emergency lookup all depend on the append-only `superseded_by` pattern. Don't "simplify" it to an update-in-place table.
- All four output agents (Report Understanding, Doctor Brief, Emergency, Language) should stream responses, not return single blocks — this is a deliberate product decision.
- Use current Gemini model names as specified (3.1 Pro / 3.5 Flash / 3.5 Flash-Lite) — do not default to older model names from training data (e.g. Gemini 1.5) without checking current availability first.
- LangGraph is the fixed orchestration choice; don't suggest swapping to a different framework without a concrete, stated reason.
- No diagnostic or treatment-recommendation logic anywhere in the system, regardless of what a feature request implies.
