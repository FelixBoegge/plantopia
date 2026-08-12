"""The plant-scoped chat page."""

import streamlit as st

from ui import bootstrap

plant_id = st.session_state.get("chat_plant_id")
if plant_id is None:
    st.info("Choose a plant from My Plants first.")
    st.stop()

st.title("💬 Chat")

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
