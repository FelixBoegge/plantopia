"""What Plantopia has learned about the owner.

A page of its own rather than an expander at the foot of My Plants. A record of
inferences a system holds about a person, and the controls to delete them, should be
somewhere the owner can reach directly — not folded away under a grid of plants,
where it is found by accident if at all.
"""

import streamlit as st

from ui import bootstrap
from ui.components.profile_panel import render_profile_panel

st.title("🧠 What Plantopia has learned about you")

st.write(
    "These are the things the agent has picked up from your diagnoses and chats, and "
    "uses when advising you. Forget any of them and it stops taking that into account."
)

profile = bootstrap.get_profile_service()
render_profile_panel(profile.all_facts(), profile.forget)
