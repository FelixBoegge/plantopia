"""Plantopia — an AI plant-health agent."""

import streamlit as st

st.set_page_config(page_title="Plantopia", page_icon="🌿", layout="centered")

pages = [
    st.Page("ui/pages/diagnose.py", title="Diagnose", icon="🔍", default=True),
]

st.navigation(pages).run()
