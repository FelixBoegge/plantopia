"""Plantopia — an AI plant-health agent."""

import streamlit as st

st.set_page_config(page_title="Plantopia", page_icon="🌿", layout="centered")

pages = [
    st.Page("ui/pages/my_plants.py", title="My Plants", icon="🌿", default=True),
    st.Page("ui/pages/diagnose.py", title="Diagnose", icon="🔍"),
    st.Page("ui/pages/plant_detail.py", title="Plant detail", icon="📋"),
    st.Page("ui/pages/chat.py", title="Chat", icon="💬"),
    st.Page("ui/pages/evaluation.py", title="Evaluation", icon="📊"),
]

st.navigation(pages).run()
