"""Renders a plant's observation/diagnosis history as a timeline."""

import streamlit as st

from services.plant_service import PlantDetail

_RECHECK_MARKER = "🔁 Re-check"


def render_timeline(detail: PlantDetail) -> None:
    """Render every diagnosis for this plant, newest first.

    Entries born of a re-check are marked as such. ``persist`` records the distinction
    on the *observation* (``kind="recheck"`` vs ``"initial"``), not the diagnosis, so
    the two have to be correlated via ``diagnosis.observation_id`` — without that the
    whole point of recording the kind is invisible to the owner, even though the chat
    agent's ``get_plant_journal`` tool already reads it.
    """
    if not detail.diagnoses:
        st.info("No diagnoses yet — start one from the Diagnose page.")
        return

    observation_kinds = {observation.id: observation.kind for observation in detail.observations}

    for diagnosis in detail.diagnoses:
        with st.container(border=True):
            when = diagnosis.created_at.strftime("%d %b %Y")
            if observation_kinds.get(diagnosis.observation_id) == "recheck":
                st.caption(_RECHECK_MARKER)
            if diagnosis.differential.is_healthy:
                st.markdown(f"**{when} — looks healthy**")
            else:
                primary = diagnosis.differential.primary
                st.markdown(f"**{when} — {primary.name}** ({primary.probability:.0%})")
            st.caption(diagnosis.differential.reasoning)
