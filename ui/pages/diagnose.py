"""The diagnosis wizard."""

import logging

import streamlit as st

from core.guards import UploadRejected
from ui import bootstrap
from ui.components.cost_badge import render_cost_badge
from ui.components.differential import render_differential
from ui.components.roadmap import render_roadmap

logger = logging.getLogger(__name__)

st.title("🌿 Diagnose a plant")

# The placeholder a plant carries from intake until the owner names it at the end.
_DEFAULT_PLANT_NAME = "My plant"

# Above this, the species guess is stated plainly and is worth suggesting as a name;
# below it the page hedges, and a hedged guess is no basis for naming the plant.
_CONFIDENT_SPECIES = 0.7


def _rotate_thread() -> None:
    """Start the next attempt on a fresh thread so an abandoned run's checkpoint
    (a rejection or a retake) never merges into the retry (U7)."""
    import uuid

    st.session_state.thread_id = uuid.uuid4().hex


def _reset() -> None:
    """Send the wizard back to the upload stage for a brand-new plant."""
    _rotate_thread()
    st.session_state.stage = "upload"
    for key in ("questions", "species", "result", "species_correction", "named_as"):
        st.session_state.pop(key, None)


def _suggested_name() -> str | None:
    """What to call this plant, taken from the identification — or ``None`` when no
    name is the honest answer.

    A species the owner corrected outranks the model's guess: if they say it is a
    rosemary, it is a rosemary. Below ``_CONFIDENT_SPECIES`` nothing is suggested at
    all — the questions step hedged about the guess, and naming the plant after a
    hedge launders that uncertainty into a label the grid then shows as fact.
    """
    correction = st.session_state.get("species_correction")
    if correction:
        return correction
    species = st.session_state.get("species")
    if species is None or species.confidence < _CONFIDENT_SPECIES:
        return None
    return species.common_name


def _render_naming(plant_id: int | None) -> None:
    """Offer the identified species as this plant's name, for the owner to confirm.

    This is the only place a plant gets named: intake no longer asks, because
    identification is the agent's job and a name typed before it has happened is a
    guess made without the answer. Naming waits until after the diagnosis rather
    than sitting inside the wizard because the species is only settled here — a
    correction typed at the questions step has been applied by now.

    The field is always offered, even when nothing confident came back. With intake
    no longer asking, skipping it for an unidentified plant would leave that plant
    stuck as "My plant" with nowhere to rename it.
    """
    if plant_id is None:
        return

    if named := st.session_state.get("named_as"):
        st.success(f"Saved as **{named}**.")
        return

    suggestion = _suggested_name()
    st.subheader("Name this plant")
    if suggestion is None:
        st.write("I could not put a confident name to this one. What would you like to call it?")
    else:
        st.write(f"I think this is **{suggestion}**. Call it something else if you prefer.")

    with st.form("name_plant"):
        chosen = st.text_input("Call it", value=suggestion or _DEFAULT_PLANT_NAME)
        saved = st.form_submit_button("Save name")

    if saved:
        try:
            bootstrap.get_plant_service().rename_plant(plant_id, name=chosen)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.named_as = chosen.strip()
            st.rerun()


# Both of the other places that needed a fresh thread id used to inline
# ``uuid.uuid4().hex`` themselves; they call _rotate_thread() now, so the rotation
# rule lives in exactly one place.
if "thread_id" not in st.session_state:
    _rotate_thread()
    st.session_state.stage = "upload"

service = bootstrap.get_service()


if st.session_state.stage == "upload":
    st.write(
        "Upload photos of the plant. Several angles help — the whole plant, a close-up "
        "of the affected part, and the soil surface."
    )

    with st.form("intake"):
        uploads = st.file_uploader(
            "Photos", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True
        )
        location_kind = st.radio("Where does it live?", ["indoor", "outdoor"], horizontal=True)
        location_text = st.text_input("Town or city (optional, helps for outdoor plants)")
        user_notes = st.text_area("Anything else worth knowing? (optional)")
        submitted = st.form_submit_button("Diagnose", type="primary")

    if submitted:
        try:
            with st.spinner("Looking at your photos…"):
                result = service.start(
                    uploads=[f.getvalue() for f in uploads or []],
                    # A placeholder until the result stage offers the identification
                    # as a name. Identification is the agent's job, so intake does
                    # not ask — but the plant needs some label while the run is in
                    # flight and if the owner abandons it before naming.
                    plant_name=_DEFAULT_PLANT_NAME,
                    location_kind=location_kind,
                    location_text=location_text or None,
                    user_notes=user_notes or None,
                    thread_id=st.session_state.thread_id,
                )
        except (UploadRejected, ValueError) as exc:
            st.error(str(exc))
        except RuntimeError as exc:
            st.error(str(exc))
        else:
            if result.status == "rejected":
                st.error(result.message)
                _rotate_thread()
            elif result.status == "retake":
                st.warning(result.message)
                _rotate_thread()
            else:
                st.session_state.questions = result.questions
                st.session_state.species = result.species
                st.session_state.stage = "questions"
                st.rerun()

elif st.session_state.stage == "questions":
    species = st.session_state.get("species")

    if species is not None:
        confidence_note = (
            "I am fairly confident"
            if species.confidence >= _CONFIDENT_SPECIES
            else "I am not certain"
        )
        st.write(f"{confidence_note} this is **{species.common_name}**.")
        correction = st.text_input(
            "If that's wrong, tell me what it actually is",
            placeholder=species.common_name,
            help="You know your plant better than a photo does — I'll trust your answer.",
        )
    else:
        correction = st.text_input("What kind of plant is this? (optional)")

    st.write(
        "A photo cannot show me how you care for this plant, and that is usually what "
        "decides between the possibilities. A few questions:"
    )

    with st.form("answers"):
        answers: dict[str, str] = {}
        for question in st.session_state.questions:
            widget_key = f"q_{question.key}"
            if question.kind == "choice":
                answers[question.key] = st.radio(question.text, question.options, key=widget_key)
            elif question.kind == "boolean":
                answers[question.key] = (
                    "yes" if st.checkbox(question.text, key=widget_key) else "no"
                )
            else:
                answers[question.key] = st.text_input(question.text, key=widget_key)
        submitted = st.form_submit_button("Get my diagnosis", type="primary")

    if submitted:
        # The correction outranks the guess when naming the plant later: if the owner
        # says it is a rosemary, it is a rosemary.
        st.session_state.species_correction = correction or None
        try:
            with st.spinner("Working through the possibilities…"):
                result = service.answer(
                    answers,
                    thread_id=st.session_state.thread_id,
                    species_override=correction or None,
                )
        except Exception:
            logger.exception("service.answer failed for thread %s", st.session_state.thread_id)
            st.error(
                "Something went wrong while finishing this diagnosis, after your photos "
                "were already analysed. Please try again — if it keeps happening, start "
                "a fresh diagnosis."
            )
        else:
            st.session_state.result = result
            st.session_state.stage = "result"
            st.rerun()

elif st.session_state.stage == "result":
    result = st.session_state.result

    if result.differential is None:
        st.error("I could not complete this diagnosis. Please try again.")
    else:
        render_differential(result.differential, low_confidence=result.low_confidence)

        if result.contagion and result.contagion.at_risk:
            st.warning(result.contagion.advice)

        if not result.differential.is_healthy:
            render_roadmap(result.roadmap)

        total_sources = len(result.retrieved) + len(result.visual_matches)
        if total_sources:
            with st.expander(f"Sources consulted ({total_sources})"):
                if result.retrieved:
                    st.caption("Matched on your described symptoms")
                    for passage in result.retrieved:
                        label = "web" if passage.doc_id.startswith("web:") else "knowledge base"
                        st.markdown(f"**{passage.doc_id}** — {passage.section} *({label})*")

                if result.visual_matches:
                    st.caption("Matched on the photograph itself")
                    for passage in result.visual_matches:
                        st.markdown(
                            f"**{passage.doc_id}** — {passage.section} "
                            f"*(visual match, {passage.score:.0%})*"
                        )

        with st.expander("What the agent did"):
            st.write(", ".join(result.tools_used) or "no tools were called")
            if result.errors:
                st.caption("Non-fatal issues: " + "; ".join(result.errors))

        render_cost_badge(result.token_usage, result.cost_usd)
        _render_naming(result.plant_id)

    st.button("Diagnose another plant", on_click=_reset)
