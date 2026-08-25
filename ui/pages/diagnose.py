"""The diagnosis wizard."""

import logging
from uuid import UUID

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
    for key in ("questions", "species", "result"):
        st.session_state.pop(key, None)


def _needs_reset() -> bool:
    """Whether this rerun should start the wizard over.

    Two cases. The first visit of a session has nothing to resume. And arriving on
    the page with a *finished* diagnosis on screen starts the next one clean, rather
    than opening on the last one's result with a button at the foot of it as the only
    way forward.

    A wizard still in flight is deliberately left where it was: its photos have
    already been analysed and paid for, and clicking the Diagnose tab is how the
    owner comes back to it.

    ``arrived_on_page`` is set in ``app.py``, where navigation is resolved, and is
    true only on the first rerun after a move — clicking around inside the wizard
    does not count as arriving, or submitting the intake form would wipe the state
    that submission just produced.
    """
    if "thread_id" not in st.session_state:
        return True
    return bool(st.session_state.get("arrived_on_page")) and st.session_state.stage == "result"


def _name_plant(plant_id: UUID | None, name: str) -> None:
    """Give the newly created plant the name chosen at the questions step.

    A rename after the fact, rather than a name threaded through the service and the
    graph: ``persist`` creates the plant from the placeholder, and its label is the
    only thing about it that needs to change.

    A failure here is logged, not raised. The diagnosis is committed by this point,
    and throwing away a result the owner waited and paid for — over a label they can
    fix later — would be a poor trade.
    """
    if plant_id is None or not name:
        return
    try:
        bootstrap.get_plant_service().rename_plant(plant_id, name=name)
    except Exception:  # noqa: BLE001 — see the docstring: never lose a diagnosis
        logger.exception("could not name plant %s %r", plant_id, name)


# Both of the other places that needed a fresh thread id used to inline
# ``uuid.uuid4().hex`` themselves; they call _rotate_thread() now, so the rotation
# rule lives in exactly one place.
#
if _needs_reset():
    _reset()

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
        chosen_name = st.text_input(
            "What should I call this plant?",
            value=species.common_name,
            help=(
                "Prefilled with what I think it is. Change it if I have it wrong, or to "
                "whatever you call this plant — this is the name it gets in My Plants."
            ),
        )
    else:
        chosen_name = st.text_input(
            "What kind of plant is this? (optional)",
            help="Whatever you put here is the name it gets in My Plants.",
        )

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
        chosen_name = chosen_name.strip()
        # Only text that differs from the guess is a correction. Sending the prefilled
        # value back would restate the same species at confidence 1.0 with its
        # scientific name dropped (DiagnosisService.answer) — turning a hedge into a
        # certainty purely because the owner left the field alone.
        guess = species.common_name if species is not None else None
        try:
            with st.spinner("Working through the possibilities…"):
                result = service.answer(
                    answers,
                    thread_id=st.session_state.thread_id,
                    species_override=chosen_name if chosen_name != guess else None,
                )
        except Exception:
            logger.exception("service.answer failed for thread %s", st.session_state.thread_id)
            st.error(
                "Something went wrong while finishing this diagnosis, after your photos "
                "were already analysed. Please try again — if it keeps happening, start "
                "a fresh diagnosis."
            )
        else:
            _name_plant(result.plant_id, chosen_name)
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

    st.button("Diagnose another plant", on_click=_reset)
