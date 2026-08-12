"""The plant-scoped chat page.

Scoped by ``selected_plant_id`` — the same session-state key Plant detail uses as
its source of truth. This page is registered as a top-level sidebar page, so it is
reachable without going through Plant detail's "Chat about this plant" button at all;
a key only that button set would keep pointing at whichever plant was opened first,
and this page would then show (and write to) the wrong plant's transcript.
"""

import streamlit as st

from ui import bootstrap

plant_id = st.session_state.get("selected_plant_id")
if plant_id is None:
    st.info("Choose a plant from My Plants first.")
    st.stop()

detail = bootstrap.get_plant_service().get_plant_detail(plant_id)
if detail is None:
    st.error("That plant no longer exists.")
    st.stop()

st.title(f"💬 Chat about {detail.plant.name}")

service = bootstrap.get_chat_service()

for message in service.history(plant_id):
    with st.chat_message(message.role):
        st.write(message.content)

prompt = st.chat_input("Ask about this plant")
if prompt:
    with st.chat_message("user"):
        st.write(prompt)
    with st.spinner("Thinking…"):
        turn = service.send(plant_id, prompt)
    with st.chat_message("assistant"):
        st.write(turn.reply)
    if turn.escalated:
        st.info("This looks worth a fresh look — see the Re-check button on this plant's page.")
