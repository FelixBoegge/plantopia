"""The diagnose node.

Produces a ranked differential rather than a single answer, because the honest
epistemic state after looking at a plant photo is usually "two or three things could
cause this, and here is how to tell them apart".
"""

import logging
from collections.abc import Callable
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.prompts.diagnose import DIAGNOSE
from agent.prompts.weather import render as render_weather
from agent.schemas import Differential
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured
from core.guards import meets_confidence_threshold, scan_for_injection, wrap_untrusted

logger = logging.getLogger(__name__)


def make_diagnose(deps: Deps) -> NodeFn:
    """Produce a differential diagnosis from everything gathered so far."""

    def diagnose(state: DiagnosisState) -> dict:
        case = _build_case(
            state,
            deps.profile_facts,
            stale_after_days=deps.settings.stale_photograph_days,
            today=deps.now().date(),
        )
        messages = [SystemMessage(DIAGNOSE), HumanMessage(case)]
        try:
            differential = invoke_structured(deps.chat_model, Differential, messages)
        except StructuredOutputFailed as exc:
            logger.warning("diagnose failed: %s", exc)
            return {"differential": None, "errors": [*state.errors, f"diagnose: {exc}"]}

        low_confidence = not meets_confidence_threshold(differential, deps.settings)
        if low_confidence:
            logger.info("diagnosis below confidence threshold: %.2f", differential.top_confidence)

        return {"differential": differential, "low_confidence": low_confidence}

    return diagnose


def _build_case(
    state: DiagnosisState,
    profile_facts: Callable[[], str],
    *,
    stale_after_days: int,
    today: date,
) -> str:
    """Assemble the case description, fencing anything that came from outside.

    The age arguments have no defaults deliberately. A default would let a call site forget
    them and produce a case that looks complete and silently never mentions a three-week-old
    photograph — which is the failure this project keeps finding in green suites.
    """
    sections: list[str] = [f"Species: {state.species_name or 'unidentified'}"]
    sections.append(f"Setting: {state.location_kind}")

    if state.symptoms:
        symptom_lines = "\n".join(
            f"- {s.description} — position: {s.position.value}, severity: {s.severity.value}"
            for s in state.symptoms.symptoms
        )
        sections.append(f"Observed symptoms:\n{symptom_lines}")
        sections.append(f"Soil surface: {state.symptoms.soil_condition or 'not visible'}")
        sections.append(f"Overall vigour: {state.symptoms.overall_vigor}")
    else:
        sections.append("Observed symptoms: could not be extracted from the photographs.")

    if state.answers:
        answer_lines = "\n".join(f"- {key}: {value}" for key, value in state.answers.items())
        sections.append(f"Owner's answers:\n{answer_lines}")

    if state.care_baseline_text:
        sections.append(state.care_baseline_text)

    if state.weather:
        sections.append(render_weather(state.weather))

    stale = _staleness(state, stale_after_days, today)
    if stale:
        sections.append(stale)

    if state.retrieved:
        sections.append(_format_passages(state.retrieved, "Reference material"))
    else:
        sections.append(
            "No reference material was retrieved. Reason from general plant physiology "
            "and lower your confidence accordingly."
        )

    if state.visual_matches:
        sections.append(
            _format_passages(
                state.visual_matches,
                "Visually similar reference material — found by matching the photograph "
                "itself against the knowledge base, independently of the symptom "
                "description above. Treat it as a second opinion: corroborating when it "
                "agrees with the described symptoms, and worth explaining when it does not",
            )
        )
    else:
        # Stated rather than omitted. The system prompt describes this section
        # unconditionally, and on the first live run the model filled the silence by
        # claiming the visual material corroborated its diagnosis — evidence the owner
        # was shown in the reasoning and that never existed.
        sections.append(
            "No photograph-matched reference material is available for this case. Do not "
            "refer to visually similar reference material in your reasoning, and do not "
            "treat its absence as evidence either way."
        )

    # Last on purpose: the owner's priors are the weakest evidence in the case and
    # should read after the photograph-derived material, not before it. An empty
    # profile appends nothing at all — no header, no placeholder — because a section
    # that describes itself and is then blank invites the model to invent
    # corroborating evidence to fill it (docs/known-limitations.md).
    #
    # Reading the profile is guarded the same way writing it is: a failed SELECT on
    # the profile connection must not cost the owner their diagnosis, so it degrades
    # to "no profile" rather than raising out of this node.
    try:
        block = profile_facts()
    except Exception as exc:  # noqa: BLE001 — a read failure here must not break diagnosis
        logger.warning("profile read failed, proceeding without it: %s", exc)
        block = ""
    if block:
        sections.append(block)

    return "\n\n".join(sections)


def _format_passages(passages: list, heading: str) -> str:
    """Fence passages as untrusted data (spec §13.2).

    Text-path and image-path passages are formatted under separate headings and never
    interleaved. Their similarity scores are on different scales, so presenting them
    as one ranked list would imply a comparison that does not hold (spec §10.4).
    """
    blocks: list[str] = []
    for passage in passages:
        matches = scan_for_injection(passage.text)
        if matches:
            logger.warning("injection patterns %s in passage %s", matches, passage.doc_id)
        blocks.append(
            wrap_untrusted(
                f"[{passage.doc_id} — {passage.section}]\n{passage.text}",
                label=passage.doc_id,
            )
        )
    return f"{heading}:\n\n" + "\n\n".join(blocks)


def _staleness(state: DiagnosisState, threshold: int, today: date) -> str:
    """Told how old the photograph is, when it is old enough to matter.

    A plant changes. Diagnosing a three-week-old photograph as though the plant were
    standing there produces advice about a plant that has since recovered or got
    considerably worse — and the confident tone is the same either way, so nothing in the
    answer would tell the owner which they were reading.

    Nothing is said about a recent photograph. A sentence on every run saying the
    photograph is fine is a sentence the model learns to skip, and it would cost tokens on
    every run to say nothing.

    Judged by ``captured_at``, which is what the owner left at the pause rather than what
    the camera recorded — they may have corrected it, and a correction that changed nothing
    would be a control that does nothing.
    """
    if state.captured_at is None:
        return ""

    age = (today - state.captured_at.date()).days
    if age <= threshold:
        return ""

    return (
        f"This photograph is {age} days old. The plant has had {age} days to change since "
        "it was taken, and may look considerably better or worse now. Diagnose what the "
        "photograph shows, but say plainly in your reasoning that the photograph is "
        f"{age} days old, that this makes the answer less reliable, and that a photograph "
        "taken today would give a better one."
    )
