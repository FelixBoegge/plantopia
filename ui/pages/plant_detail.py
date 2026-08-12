"""The Plant detail page: timeline, roadmap checklist, feedback, and re-check."""

import streamlit as st

from core.guards import UploadRejected
from services.diagnosis_service import FinalResult, StartResult
from ui import bootstrap
from ui.components.feedback import render_feedback_prompt
from ui.components.roadmap_checklist import render_roadmap_checklist
from ui.components.timeline import render_timeline

plant_id = st.session_state.get("selected_plant_id")
if plant_id is None:
    st.info("Choose a plant from My Plants first.")
    st.stop()

# The re-check keys below are bare session-state keys, not scoped by plant. Without
# this reset, finishing a re-check on one plant and then navigating (within the same
# session) to a different plant would carry the first plant's stale recheck_stage /
# recheck_result over onto the second plant's page.
if st.session_state.get("_recheck_owner_plant_id") != plant_id:
    st.session_state.pop("recheck_stage", None)
    st.session_state.pop("recheck_result", None)
    st.session_state._recheck_owner_plant_id = plant_id

service = bootstrap.get_plant_service()
detail = service.get_plant_detail(plant_id)
if detail is None:
    st.error("That plant no longer exists.")
    st.stop()

st.title(f"🌿 {detail.plant.name}")

render_timeline(detail)

st.subheader("Treatment plan")
render_roadmap_checklist(
    detail.roadmap_steps,
    on_mark=lambda step_id, status: service.mark_roadmap_step(step_id, status=status),
)

if detail.feedback_due:
    render_feedback_prompt(
        on_submit=lambda rating, did_it_help, text: service.submit_feedback(
            diagnosis_id=detail.diagnoses[0].id,
            rating=rating,
            did_it_help=did_it_help,
            free_text=text or None,
        )
    )

st.divider()
st.subheader("Re-check")

if "recheck_stage" not in st.session_state:
    st.session_state.recheck_stage = "closed"

if st.session_state.recheck_stage == "closed":
    if st.button("Re-check this plant"):
        st.session_state.recheck_stage = "upload"
        st.rerun()
elif st.session_state.recheck_stage == "upload":
    uploads = st.file_uploader(
        "New photos", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True
    )
    notes = st.text_area("Anything else worth noting? (optional)", key="recheck_notes")
    if st.button("Submit re-check"):
        diagnosis_service = bootstrap.get_service()
        try:
            with st.spinner("Looking at your photos…"):
                result = diagnosis_service.start_recheck(
                    plant_id=plant_id,
                    uploads=[f.getvalue() for f in uploads or []],
                    user_notes=notes or None,
                    thread_id=(
                        f"recheck-{plant_id}-{detail.diagnoses[0].id if detail.diagnoses else 0}"
                    ),
                )
        except (UploadRejected, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state.recheck_result = result
            st.session_state.recheck_stage = "closed"
            st.rerun()

if st.session_state.get("recheck_result") is not None:
    result = st.session_state.recheck_result
    if isinstance(result, StartResult) and result.status == "rejected":
        st.error(result.message)
    elif isinstance(result, StartResult) and result.status == "retake":
        st.warning(result.message)
    elif isinstance(result, FinalResult):
        st.success("Re-check complete.")
        if result.verdict is not None:
            # Rendered with the underscore spaced out ("new problem"), matching how
            # README words the four verdicts, rather than mapped to invented prose.
            st.markdown(f"**Verdict:** {result.verdict.replace('_', ' ')}")
            if result.verdict_reasoning:
                st.caption(result.verdict_reasoning)
        if result.differential is not None:
            st.write(result.differential.reasoning)

# No extra session state to set: the Chat page reads ``selected_plant_id``, which is
# what got us onto this page in the first place.
if st.button("Chat about this plant"):
    st.switch_page("ui/pages/chat.py")
