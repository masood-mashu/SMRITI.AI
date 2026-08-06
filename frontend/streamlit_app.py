import os

import requests
import streamlit as st


API_URL = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="Smriti", page_icon="🩺")
st.title("Smriti")
st.caption("Never repeat your medical history again.")

uploaded = st.file_uploader("Upload a medical report", type=["pdf", "png", "jpg", "jpeg"])
if uploaded and st.button("Process report"):
    with st.spinner("Sending report to Smriti…"):
        response = requests.post(
            f"{API_URL}/reports",
            files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
            timeout=60,
        )
    if response.ok:
        st.success("Report accepted by the agent graph.")
        st.json(response.json())
    else:
        st.error(f"Backend error ({response.status_code}): {response.text}")

st.divider()
st.subheader("On-demand outputs")
if st.button("Generate doctor brief"):
    response = requests.post(f"{API_URL}/brief", timeout=60)
    st.json(response.json())
if st.button("Generate emergency card"):
    response = requests.post(f"{API_URL}/emergency", timeout=60)
    st.json(response.json())
language = st.selectbox("Translation language", ["en", "hi", "kn"])
if st.button("Translate"):
    response = requests.post(f"{API_URL}/translate", params={"language": language}, timeout=60)
    st.json(response.json())
