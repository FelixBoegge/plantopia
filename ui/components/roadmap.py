"""Renders a treatment roadmap as a checklist."""

import streamlit as st

from agent.schemas import Roadmap
from ui.components._ipm_labels import TIER_LABEL


def render_roadmap(roadmap: Roadmap | None) -> None:
    """Render the treatment plan, or say plainly that there isn't one."""
    if roadmap is None:
        st.info("No treatment plan was produced for this diagnosis.")
        return

    st.subheader("Treatment plan")
    st.caption("Least invasive first — most plant problems are caused by conditions.")

    for step in roadmap.steps:
        due = "today" if step.day_offset == 0 else f"in {step.day_offset} days"
        with st.container(border=True):
            st.markdown(f"**{step.ordinal}. {step.action}**")
            st.caption(f"{TIER_LABEL[step.tier]} · {due}")
            st.markdown(f"*Why:* {step.rationale}")
            st.markdown(f"*You'll know it worked when:* {step.success_signal}")
