"""The human-in-the-loop node.

The graph cannot reach a diagnosis without passing through here. That is deliberate:
the facts that decide between the common causes are not visible in a photograph, so
asking is not a nicety, it is a precondition for being right.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.prompts.context import SELECT_QUESTIONS
from agent.schemas import Question, QuestionSet, SpeciesGuess, SpeciesMethod
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured

logger = logging.getLogger(__name__)

WATERING_QUESTION = Question(
    key="watering",
    text="How often do you water this plant, and when did you last water it?",
    kind="text",
)

DRAINAGE_QUESTION = Question(
    key="drainage",
    text="Does the pot have drainage holes, and does water sit in a saucer underneath?",
    kind="choice",
    options=[
        "Drainage holes, no saucer",
        "Drainage holes, water sits in a saucer",
        "No drainage holes",
        "Planted directly in the ground",
    ],
)

LOCATION_QUESTION = Question(
    key="location",
    text="Which town or city is the plant in? Recent weather may be part of the picture.",
    kind="text",
)

ALWAYS_ASK: tuple[Question, ...] = (WATERING_QUESTION, DRAINAGE_QUESTION)
ALWAYS_ASK_KEYS: frozenset[str] = frozenset(q.key for q in ALWAYS_ASK)


def select_questions(deps: Deps, state: DiagnosisState) -> list[Question]:
    """Choose the questions to ask for this case.

    Watering and drainage are always asked: they discriminate between the most common
    disorders and owners almost never volunteer them. An outdoor plant with no known
    location is also asked where it is, because weather history depends on it.

    Mandatory questions are placed first so the configured cap can never evict them.
    The cap itself is clamped to be no smaller than the mandatory count, so even a
    configured maximum below ``len(ALWAYS_ASK)`` cannot cut into that block.
    """
    questions: list[Question] = list(ALWAYS_ASK)

    if state.location_kind == "outdoor" and not state.location_text:
        questions.append(LOCATION_QUESTION)

    questions.extend(_model_questions(deps, state))

    seen: set[str] = set()
    unique: list[Question] = []
    for question in questions:
        if question.key not in seen:
            seen.add(question.key)
            unique.append(question)

    cap = max(deps.settings.max_clarifying_questions, len(ALWAYS_ASK))
    return unique[:cap]


def _model_questions(deps: Deps, state: DiagnosisState) -> list[Question]:
    """Ask the model for case-specific questions. Failure yields none."""
    symptom_lines = (
        "\n".join(
            f"- {s.description} ({s.position.value}, {s.severity.value})"
            for s in state.symptoms.symptoms
        )
        if state.symptoms
        else "- not extracted"
    )

    prompt = (
        f"Plant: {state.species_name or 'unidentified'}\n"
        f"Setting: {state.location_kind}\n"
        f"Observed symptoms:\n{symptom_lines}\n"
        f"Soil surface: {state.symptoms.soil_condition if state.symptoms else 'unknown'}"
    )

    try:
        result = invoke_structured(
            deps.chat_model,
            QuestionSet,
            [SystemMessage(SELECT_QUESTIONS), HumanMessage(prompt)],
        )
    except StructuredOutputFailed as exc:
        logger.warning("question selection failed, falling back to mandatory only: %s", exc)
        return []

    return result.questions


def make_select_questions(deps: Deps) -> NodeFn:
    """Choose the questions and write them to state, one graph step before the halt.

    Kept as a separate node — and therefore a separate checkpointed step — from
    ``gather_context``. LangGraph replays a node's body from the top whenever it
    resumes past an ``interrupt`` inside that same node, so any model call placed
    before the ``interrupt`` in ``gather_context`` would fire a second time on every
    resume. Selecting the questions here means that work is already committed to the
    checkpoint by the time ``gather_context`` runs, so resuming never repeats it.
    """

    def select_questions_node(state: DiagnosisState) -> dict:
        if state.answers or state.questions:
            return {}
        return {"questions": select_questions(deps, state)}

    return select_questions_node


def _method_of(name: str, candidates) -> SpeciesMethod:
    """Which method produced the candidate with this name.

    ``TYPED`` when nothing matches, because the only route to a species that was never
    offered is a person having said it.
    """
    for candidate in candidates:
        if candidate.common_name.casefold() == name.casefold():
            return candidate.method
    return SpeciesMethod.TYPED


def make_gather_context(deps: Deps) -> NodeFn:
    """Halt until the user answers the questions ``select_questions`` chose.

    ``interrupt`` suspends the graph. The service layer resumes it with a
    ``Command(resume=answers)`` once the user has responded. This node does nothing
    but read already-checkpointed state and call ``interrupt``, so replaying it on
    resume has no side effect worth avoiding.
    """

    def gather_context(state: DiagnosisState) -> dict:
        if state.answers:
            return {}

        given = interrupt(
            {
                "questions": [q.model_dump() for q in state.questions],
                # Only when there is a decision to make. One candidate means every method,
                # and the owner if they said anything, named the same plant — asking
                # somebody to confirm what nobody disputed is an interruption, not a
                # choice. The client renders this block only when it is present.
                **(
                    {"identification": [c.model_dump() for c in state.candidates]}
                    if len(state.candidates) > 1
                    else {}
                ),
            }
        )

        # A resume payload is either the answers on their own — which is what it was before
        # a species could be chosen, and what an older client still sends — or a mapping
        # carrying both. Reading both shapes rather than requiring the new one keeps a run
        # that was paused before a deployment resumable after it.
        return _resumed(given, state.candidates)

    return gather_context


def _resumed(given, candidates=()) -> dict:
    """What a resume payload means for state.

    The chosen species is written here rather than in ``select_questions`` for the reason
    that whole node exists: this one does nothing but read already-checkpointed state and
    call ``interrupt``, so replaying it on resume has no side effect. ``select_questions``
    runs *before* the interrupt and would have to guess.
    """
    if not isinstance(given, dict):
        return {"answers": {}}

    answers = given.get("answers")
    if answers is None:
        # The old shape: the mapping *is* the answers.
        return {"answers": dict(given)}

    chosen = given.get("species")
    if not chosen:
        return {"answers": dict(answers)}

    name = chosen.get("common_name") or "Unknown"
    return {
        "answers": dict(answers),
        "species": SpeciesGuess(
            common_name=name,
            scientific_name=chosen.get("scientific_name"),
            confidence=float(chosen.get("confidence") or 0.0),
        ),
        # Looked up here rather than taken from what the client sent. The client knows which
        # candidate it offered, but this field is the record used to attribute a wrong
        # diagnosis afterwards, and a record whose provenance is whatever a client claimed
        # is not evidence of anything.
        "species_method": _method_of(name, candidates),
        # Somebody looked at the candidates and picked one. That is a different fact from
        # the leading candidate happening to be right, and the difference is what makes a
        # wrong diagnosis attributable later.
        "species_confirmed": True,
    }
