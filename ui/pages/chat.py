"""The plant-scoped chat page.

Scoped by ``selected_plant_id`` — the same session-state key Plant detail uses as
its source of truth. This page is registered as a top-level sidebar page, so it is
reachable without going through Plant detail's "Chat about this plant" button at all;
a key only that button set would keep pointing at whichever plant was opened first,
and this page would then show (and write to) the wrong plant's transcript.
"""

import streamlit as st

from ui import bootstrap

# Which plant's chat last escalated, if any. Scoped by plant id rather than a bare
# boolean so the handoff offer cannot follow the user onto a different plant's chat.
_ESCALATION_KEY = "chat_escalation_plant_id"

plant_id = st.session_state.get("selected_plant_id")
if plant_id is None:
    st.info("Choose a plant from My Plants first.")
    st.stop()

service = bootstrap.get_chat_service()

# A single-row lookup (services.chat_service.ChatService.get_plant) rather than
# bootstrap.get_plant_service().get_plant_detail(), which also queries observations,
# diagnoses, roadmap steps and feedback — all wasted just to read the plant's name
# for the page title.
plant = service.get_plant(plant_id)
if plant is None:
    st.error("That plant no longer exists.")
    st.stop()

st.title(f"💬 Chat about {plant.name}")


def _render_tool_calls(tool_calls: list[dict]) -> None:
    """Show what the agent looked up, collapsed by default (design spec §5)."""
    with st.expander(f"Tool calls ({len(tool_calls)})"):
        for call in tool_calls:
            st.markdown(f"**{call.get('name', 'unknown tool')}**")
            if call.get("args"):
                st.caption(", ".join(f"{k}: {v}" for k, v in call["args"].items()))
            if call.get("result"):
                st.caption(call["result"])


for message in service.history(plant_id):
    with st.chat_message(message.role):
        st.write(message.content)
        if message.tool_calls:
            _render_tool_calls(message.tool_calls)

prompt = st.chat_input("Ask about this plant")
if prompt:
    with st.chat_message("user"):
        st.write(prompt)
    with st.spinner("Thinking…"):
        turn = service.send(plant_id, prompt)
    with st.chat_message("assistant"):
        st.write(turn.reply)
    # Recorded rather than rendered inline, so the handoff below survives the rerun a
    # button click causes. Re-evaluated every turn: if the newest answer no longer
    # escalates, the offer goes away with it.
    if turn.escalated:
        st.session_state[_ESCALATION_KEY] = plant_id
    else:
        st.session_state.pop(_ESCALATION_KEY, None)

# Deliberately outside the ``if prompt:`` block above. Clicking a button is its own
# rerun, and on that rerun ``st.chat_input`` returns None — a button rendered only
# inside that block would vanish before its click could ever be handled.
if st.session_state.get(_ESCALATION_KEY) == plant_id:
    st.info("This looks worth a fresh look — click below to upload a new photo.")
    if st.button("Upload a new photo"):
        # A diagnosis cannot start without photographs, so escalation hands the owner
        # straight into the re-check upload form rather than describing where to find
        # it. Priming plant_detail.py's own stage key (and its ownership marker, which
        # would otherwise clear the stage on arrival) is what makes the page open
        # already-expanded instead of at its "Re-check this plant" button.
        st.session_state.selected_plant_id = plant_id
        st.session_state.recheck_stage = "upload"
        st.session_state._recheck_owner_plant_id = plant_id
        st.session_state.pop("recheck_result", None)
        st.session_state.pop(_ESCALATION_KEY, None)
        st.switch_page("ui/pages/plant_detail.py")
