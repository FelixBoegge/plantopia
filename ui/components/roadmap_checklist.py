"""Renders a plant's roadmap steps as a tickable checklist.

Distinct from ``ui/components/roadmap.py``'s ``render_roadmap``: that one is a
read-only render of a fresh ``Roadmap`` straight off a diagnosis; this one drives
persisted, individually-markable ``RoadmapStepRecord`` rows.
"""

from collections.abc import Callable

import streamlit as st

from data.repositories.roadmap import RoadmapStepRecord

_TIER_LABEL = {1: "Cultural", 2: "Mechanical", 3: "Biological", 4: "Chemical"}


def render_roadmap_checklist(
    steps: list[RoadmapStepRecord],
    *,
    on_mark: Callable[[int, str], None],
) -> None:
    """Render every step as a checkbox; ticking a pending step calls ``on_mark``."""
    if not steps:
        st.info("No roadmap steps recorded for this plant yet.")
        return

    for step in steps:
        checked = st.checkbox(
            f"{step.action}",
            value=step.status == "done",
            key=f"roadmap_step_{step.id}",
        )
        st.caption(f"{_TIER_LABEL[int(step.tier)]} · due {step.due_date.strftime('%d %b')}")

        if checked and step.status == "pending":
            on_mark(step.id, "done")
        elif not checked and step.status == "done":
            on_mark(step.id, "pending")
