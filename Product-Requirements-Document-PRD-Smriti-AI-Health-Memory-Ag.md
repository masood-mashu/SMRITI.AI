# Product Requirements Document (PRD): Smriti — AI Health Memory Agent

## 1. Executive Summary
**Smriti** is a personal AI Health Memory Agent designed for the AI Agent Builder Series 2026 Grand Finale. Its core promise is to ensure patients "never repeat their medical history again." Unlike standard document summarizers or chatbots, Smriti acts as a patient-owned "AI Operating System for Health," building a structured, longitudinal, and cumulative memory from uploaded medical reports (photos, PDFs, scans). It uses a multi-agent architecture to generate clinician-ready briefs, emergency profiles, and plain-language explanations in regional languages.

## 2. Problem Statement
Patients face a fragmented healthcare experience where they must repeatedly explain their medical history, allergies, and medications to different providers. Existing digital health tools are often siloed, document-centric rather than data-centric, or provide generic chat interfaces that do not maintain a growing, structured "memory" of a patient's health over time.

## 3. Goals & Objectives
*   **Cumulative Memory:** Build a system that merges new medical data into a persistent, longitudinal profile rather than just storing files.
*   **Clinician Utility:** Generate concise, accurate summaries that flag contradictions or trends for doctors.
*   **Accessibility:** Provide instant, plain-language explanations and translations into regional Indian languages (Hindi, Kannada).
*   **Emergency Readiness:** Surface critical, life-saving information (allergies, chronic conditions) in a single tap.
*   **Patient Ownership:** Maintain a system that is fed and controlled by the patient, independent of hospital EHR integrations.

## 4. Target Users / Stakeholders
*   **Primary Users:** Patients and caregivers managing chronic conditions, multiple specialists, or elderly family members.
*   **Secondary Users (Consumers of Output):** 
    *   **Doctors:** Receiving clinical briefs to save time during consultations.
    *   **Emergency Responders:** Accessing critical health data in urgent scenarios.

## 5. Functional Requirements

### 5.1. Report Ingestion & Understanding
*   **Multimodal Extraction:** Support for photos, PDFs, and scans of medical reports.
*   **Native Multimodal OCR:** Use Gemini 3.1 Pro’s native vision capabilities to extract structured facts (conditions, medications, allergies, lab values, dates) without external OCR libraries.
*   **Live Streaming Explanation:** As a report is processed, the system must stream a plain-language explanation of the findings back to the UI immediately.

### 5.2. Health Memory Management
*   **Longitudinal Merging:** New extractions must be merged into the existing profile using an append-only, historied pattern (no overwriting).
*   **Living Health Graph:** Maintain relationships between conditions, medications, and lab results over time.
*   **Timeline View:** Display a chronological history of health events and data points.

### 5.3. Specialized Agent Outputs
*   **Doctor Brief:** Generate a clinical summary and proactively flag contradictions (e.g., a medication discontinued in one report but appearing in another).
*   **Emergency Card:** Generate a high-speed, structured card containing critical info (allergies, blood type, emergency contacts).
*   **Language Translation:** Translate any output into plain language and regional languages (starting with Hindi and Kannada).

### 5.4. User Interface
*   **Streamlit-based UI:** A clean interface for file uploads, timeline visualization, and viewing agent outputs.
*   **Streaming Responses:** All agent outputs (Explanation, Brief, Card, Translation) must stream live to the UI to enhance demo responsiveness.

## 6. Non-Functional Requirements
*   **Performance:** Low-latency streaming for the "Explanation" beat to ensure a smooth live demo.
*   **Accuracy:** High-precision extraction of medical facts using Gemini 3.1 Pro.
*   **Scalability:** Application must be containerized and auto-scalable via Cloud Run.
*   **Reliability:** Use relational integrity (Postgres) to ensure the health timeline remains consistent.
*   **Compliance Framing:** Explicitly state the system is not a diagnostic tool; it is an organizational and explanatory aid.

## 7. System Architecture Overview
The system follows a **Stateful Multi-Agent Graph** architecture orchestrated by **LangGraph** and **FastAPI**.
1.  **Intake:** User uploads to Streamlit UI -> FastAPI.
2.  **Extraction:** **Report Understanding Agent** (Gemini 3.1 Pro) extracts data and streams explanation.
3.  **Memory:** **Memory Agent** (SQLModel) merges data into **Postgres**.
4.  **Fan-out:** Memory Agent triggers downstream agents:
    *   **Doctor Brief Agent** (Gemini 3.5 Flash) + **Vertex AI Vector Search** for history lookup.
    *   **Emergency Agent** (Gemini 3.5 Flash-Lite) for fast structured lookup.
    *   **Language Agent** (Gemini 3.5 Flash) for translation.
5.  **Output:** All agents stream results back to the UI via WebSockets/Streaming endpoints.

## 8. Tech Stack
*   **LLMs:** 
    *   Gemini 3.1 Pro (Extraction & Reasoning)
    *   Gemini 3.5 Flash (Summarization & Translation)
    *   Gemini 3.5 Flash-Lite (Emergency Card Generation)
*   **SDK:** Vertex AI SDK (`google-cloud-aiplatform`)
*   **Orchestration:** LangGraph, FastAPI
*   **Frontend:** Streamlit
*   **Databases:** 
    *   Postgres (Cloud SQL) with SQLModel (Structured Source of Truth)
    *   Vertex AI Vector Search (Semantic History Lookup)
*   **Infrastructure:** GCP Cloud Run, Google Cloud Storage

## 9. Data Requirements
### 9.1. Schema Design (Append-Only)
The system uses a `superseded_by` pattern to maintain full history.
*   **`patients`**: Core user data.
*   **`reports`**: Metadata and raw JSON extractions from uploaded files.
*   **`health_facts`**: The core "Memory" table. Stores conditions, medications, and lab values. Includes `is_emergency_relevant` flags and `superseded_by` self-references to track changes over time.
*   **`contradictions`**: Stores AI-detected discrepancies between historical and new data.

## 10. API Specifications
*   **`POST /upload`**: Accepts multipart file uploads, triggers the LangGraph workflow.
*   **`GET /stream/explanation`**: WebSocket/Streaming endpoint for real-time extraction feedback.
*   **`GET /stream/brief`**: Streaming endpoint for clinical summaries.
*   **`GET /stream/emergency`**: Streaming endpoint for emergency card data.
*   **`GET /stream/translate`**: Streaming endpoint for regional language output.

## 11. Security Requirements
*   **Authentication:** Minimal single-user authentication for hackathon demo purposes.
*   **Data Protection:** Framing as a "Patient-Owned" vault.
*   **Safety Rails:** System must include explicit disclaimers that it does not provide medical diagnoses or treatment recommendations.

## 12. Deployment & Infrastructure
*   **Environment:** Google Cloud Platform (GCP).
*   **Compute:** Cloud Run for hosting the FastAPI/LangGraph backend and Streamlit frontend.
*   **CI/CD:** Automated deployment pipeline set up during prep days to ensure every push updates the live demo URL.
*   **Vector Indexing:** Vertex AI Vector Search index provisioned during prep days.

## 13. Success Metrics
*   **Extraction Accuracy:** Correct identification of medications and dosages from scanned reports.
*   **Latency:** Streaming explanation starts within <3 seconds of upload.
*   **Contradiction Detection:** Successful flagging of discontinued medications during the demo.
*   **Demo Stability:** Zero failures during the live 12-hour final presentation.

## 14. Timeline & Milestones
*   **Phase 1 (Prep):** 
    *   Implement Postgres schema and SQLModel logic.
    *   Build Report Understanding Agent with Gemini 3.1 Pro native multimodal.
    *   Set up LangGraph orchestration and Cloud Run CI/CD.
    *   Seed demo profile with 3-5 historical reports.
*   **Phase 2 (Final 12 Hours - Aug 8):**
    *   UI/UX polish.
    *   Harden streaming connections.
    *   End-to-end demo rehearsals.
    *   Prepare backup pre-loaded samples.

## 15. Open Questions & Risks
*   **Risk:** Live OCR failure on stage due to poor lighting or unfamiliar document formats.
    *   *Mitigation:* Pre-load a "clean" sample report as a fallback.
*   **Risk:** Rate limits on Vertex AI during the hackathon.
    *   *Mitigation:* Use Vertex AI SDK (higher limits) and implement basic retry logic.
*   **Risk:** Complexity of the "Living Health Graph" logic.
    *   *Mitigation:* Fallback to a structured tabular timeline if graph relationships become unstable.