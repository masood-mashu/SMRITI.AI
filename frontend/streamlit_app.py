import os
from uuid import uuid4

import requests
import streamlit as st


API_URL = os.getenv("API_URL", "http://localhost:8000")
SOURCE_TYPES = {
    "Other": "other",
    "Lab result": "lab_result",
    "Discharge summary": "discharge_summary",
    "Prescription": "prescription",
}


def api_params() -> dict[str, str]:
    return {"patient_id": st.session_state.patient_id}


def request_json(method: str, path: str, **kwargs) -> dict:
    response = requests.request(method, f"{API_URL}{path}", timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f"Backend error ({response.status_code}): {response.text}")
    return response.json()


if "patient_id" not in st.session_state:
    st.session_state.patient_id = str(uuid4())

st.set_page_config(page_title="Smriti", page_icon="🩺")
st.title("Smriti")
st.caption("Never repeat your medical history again.")
st.caption(f"Demo patient: `{st.session_state.patient_id}`")

st.header("Add to health memory")
source_label = st.selectbox("Report type", list(SOURCE_TYPES))
uploaded = st.file_uploader("Upload a medical report", type=["pdf", "png", "jpg", "jpeg", "txt"])
use_fixture = st.checkbox(
    "Use synthetic development fixture",
    help="Opt in to sample facts until Gemini extraction is connected.",
)

if uploaded and st.button("Process report", type="primary"):
    try:
        result = request_json(
            "POST",
            "/reports",
            params={
                **api_params(),
                "source_type": SOURCE_TYPES[source_label],
                "fixture": use_fixture,
            },
            files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
        )
        st.success("Report accepted and merged into health memory.")
        graph = result["graph"]
        st.info(graph.get("explanation", "Report processed."))
        st.caption(
            f"Provider: {graph.get('extraction_provider', 'unknown')} · "
            f"PII redactions: {graph.get('pii_redactions', 0)}"
        )
    except RuntimeError as exc:
        st.error(str(exc))


st.header("Health timeline")
if st.button("Refresh timeline"):
    try:
        timeline = request_json("GET", "/timeline", params=api_params())
        facts = timeline.get("facts", [])
        if facts:
            st.dataframe(facts, use_container_width=True, hide_index=True)
            grouped: dict[str, list[str]] = {}
            for fact in facts:
                state = "current" if fact["superseded_by"] is None else "superseded"
                grouped.setdefault(fact["fact_key"], []).append(
                    f"{fact['effective_date']}: {fact['fact_value']} ({state})"
                )
            st.subheader("Grouped by fact")
            st.dataframe(
                [{"fact_key": key, "history": " → ".join(values)} for key, values in grouped.items()],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No facts have been recorded for this patient yet.")

        contradictions = timeline.get("contradictions", [])
        if contradictions:
            st.warning("Contradictions to review")
            for item in contradictions:
                st.write(f"- {item['description']}")
    except RuntimeError as exc:
        st.error(str(exc))


st.header("On-demand outputs")
col_brief, col_emergency, col_language = st.columns(3)
with col_brief:
    if st.button("Doctor brief"):
        try:
            result = request_json("POST", "/brief", params=api_params())
            st.text(result["graph"]["doctor_brief"])
        except RuntimeError as exc:
            st.error(str(exc))
with col_emergency:
    if st.button("Emergency card"):
        try:
            result = request_json("POST", "/emergency", params=api_params())
            st.text(result["graph"]["emergency_card"])
        except RuntimeError as exc:
            st.error(str(exc))
with col_language:
    language = st.selectbox("Language", ["en", "hi", "kn"], key="output_language")
    if st.button("Translate"):
        try:
            result = request_json(
                "POST",
                "/translate",
                params={**api_params(), "language": language},
            )
            st.text(result["graph"]["translation"])
        except RuntimeError as exc:
            st.error(str(exc))
