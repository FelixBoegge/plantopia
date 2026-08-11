"""Renders a plant's observation/diagnosis history as a timeline."""

import streamlit as st

from services.plant_service import PlantDetail


def render_timeline(detail: PlantDetail) -> None:
    """Render every diagnosis for this plant, newest first."""
    if not detail.diagnoses:
        st.info("No diagnoses yet — start one from the Diagnose page.")
        return

    for diagnosis in detail.diagnoses:
        with st.container(border=True):
            when = diagnosis.created_at.strftime("%d %b %Y")
            if diagnosis.differential.is_healthy:
                st.markdown(f"**{when} — looks healthy**")
            else:
                primary = diagnosis.differential.primary
                st.markdown(f"**{when} — {primary.name}** ({primary.probability:.0%})")
            st.caption(diagnosis.differential.reasoning)
