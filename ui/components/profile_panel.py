"""Shows the owner what the agent believes about them, and lets them delete it."""

from collections.abc import Callable

import streamlit as st

from data.repositories.profile import ProfileFact


def render_profile_panel(facts: list[ProfileFact], on_delete: Callable[[str], None]) -> None:
    """Render every stored fact with its provenance, and a delete control each.

    Confidence and ``source`` are shown rather than hidden: a system that keeps
    inferences about a person should show which are inferences and how strongly
    they are held.
    """
    if not facts:
        st.caption("Nothing learned yet — facts appear here after a few diagnoses or chats.")
        return

    for fact in facts:
        left, right = st.columns([6, 1])
        left.markdown(f"**{fact.fact}**")
        left.caption(
            f"{fact.source} · confidence {fact.confidence:.1f} · "
            f"last confirmed {fact.last_confirmed:%d %b %Y}"
        )
        if right.button("Forget", key=f"forget-{fact.fact}"):
            on_delete(fact.fact)
            st.rerun()
