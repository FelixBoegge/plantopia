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
from agent.schemas import Question, QuestionSet
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

        answers = interrupt({"questions": [q.model_dump() for q in state.questions]})
        return {"answers": dict(answers or {})}

    return gather_context
