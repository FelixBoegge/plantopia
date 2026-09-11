"""The human-in-the-loop node.

The graph cannot reach a diagnosis without passing through here. That is deliberate:
the facts that decide between the common causes are not visible in a photograph, so
asking is not a nicety, it is a precondition for being right.
"""

import logging
from datetime import UTC, date, datetime

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

# The key on its own, because the question itself is now built per run — its prefill and
# whether it is required both depend on the plant — while anything that only wants to say
# "the location one" still wants a name rather than a string literal.
LOCATION_KEY = "location"

# Asked only when a photograph declared a date, which is why it is not in `ALWAYS_ASK`.
# With nothing detected the upload date is the honest answer and asking would be adding a
# control that earns nothing — nobody knows the date of a photograph better than the
# photograph, except when the photograph is somebody else's.
CAPTURE_KEY = "captured_at"

# What a prefilled answer is told to say about itself.
#
# "Recorded by your camera" rather than "read from your photograph", and the distinction is
# real rather than stylistic: the identification chooser says "read from your photo" about a
# species the vision model inferred from the pixels, while this is data the camera itself
# wrote into the file. Two sentences that sound alike, on the same screen, describing
# different kinds of knowing — and the first version of this collided with that one badly
# enough that a browser test could not tell them apart either.
FROM_THE_PHOTOGRAPH = "Recorded by your camera"

# Required by the reverse-geocoding service's terms wherever its data is shown. Kept beside
# the phrase that carries it so the two cannot drift apart.
PLACE_NAME_CREDIT = "OpenStreetMap contributors"


def capture_question(state: DiagnosisState, today: date) -> Question:
    """When the photograph was taken. Always asked, and always carrying a date.

    Every diagnosis is read against a stretch of weather, and which stretch depends entirely
    on this. So the field is never empty: it holds what the photograph declared, or today,
    and somebody who knows better changes it.

    Two reasons it is asked even when the photograph knew. A photograph forwarded from a
    message carries its original sender's date, and one from a camera whose clock was never
    set carries nonsense — neither can be told from a right answer automatically, and both
    move the weather window somewhere the plant has never been.

    And two reasons it is asked when the photograph knew nothing. Today is a guess, and a
    guess a person can see is a guess a person can fix; the alternative is a silent
    assumption that quietly decides part of the answer. It is also the *common* case —
    messaging apps strip metadata and browser capture rarely has any — so the field being
    present only sometimes would make it a surprise rather than a habit.
    """
    declared = state.captured_at.date() if state.captured_at else None

    return Question(
        key=CAPTURE_KEY,
        text="When was the photograph taken?",
        kind="date",
        prefill=(declared or today).isoformat(),
        prefill_note=(
            FROM_THE_PHOTOGRAPH
            if declared
            else "Your camera did not record one — change this if the photograph is older"
        ),
        # It has to carry one. An empty date is not a smaller answer than a wrong one, it
        # is no weather at all.
        required=True,
    )


def location_question(state: DiagnosisState, place: str | None) -> Question:
    """Where the plant is, asked here rather than before the run started.

    Nobody is asked this on the upload form any more: the photograph usually knows, and
    asking somebody to type what the file already says is asking them to do the machine's
    work. Where it does not know, this is one field among several at a pause that was
    happening anyway rather than a question standing on its own.

    Prefilled with whatever is known — a place read from the photograph, or the location a
    plant already carries from a previous run. Required only outdoors, where weather
    frequently *is* the diagnosis and its absence costs a real part of the answer; indoors
    the connection is weak enough that demanding one would be demanding it for nothing.
    """
    prefill = place or state.location_text
    return Question(
        key=LOCATION_KEY,
        text="Which town or city is the plant in? Recent weather may be part of the picture.",
        kind="text",
        prefill=prefill,
        prefill_note=_where_the_place_came_from(place, prefill),
        required=state.location_kind == "outdoor",
    )


def _where_the_place_came_from(place: str | None, prefill: str | None) -> str | None:
    """The phrase shown under a prefilled location.

    The credit travels with the name rather than sitting on the page, because a name from
    the reverse-geocoding service comes with terms and a name the plant already carried does
    not. Tying it to the datum is what stops a later screen showing one without the other.
    """
    if place:
        return f"{FROM_THE_PHOTOGRAPH}, named by {PLACE_NAME_CREDIT}"
    if prefill:
        return "Where this plant was last time"
    return None


ALWAYS_ASK: tuple[Question, ...] = (WATERING_QUESTION, DRAINAGE_QUESTION)
ALWAYS_ASK_KEYS: frozenset[str] = frozenset(q.key for q in ALWAYS_ASK)


def select_questions(deps: Deps, state: DiagnosisState, place: str | None = None) -> list[Question]:
    """Choose the questions to ask for this case.

    Four are always asked. Watering and drainage discriminate between the most common
    disorders and owners almost never volunteer them. Where the plant is and when the
    photograph was taken decide which stretch of weather the diagnosis is read against —
    both prefilled from what is known, so the usual work of answering them is none.

    **The cap governs the model's questions, not these four.** It used to govern the whole
    list, which was the same thing when two of the four did not exist: a configured maximum
    of four now leaves the model nothing, and the model's questions are the ones that
    discriminate in the specific case rather than in general. So the fixed fields are
    outside it, and what "at most four clarifying questions" limits is how many *the agent
    thinks of* — which is what somebody setting it is trying to bound.
    """
    # Where and when lead, because on screen they sit directly under the species chooser and
    # the three of them are one thought: what this plant is, where it is, and when it was
    # photographed. Watering and drainage are a different subject and follow.
    fixed: list[Question] = [
        location_question(state, place if place is not None else _place(deps, state)),
        capture_question(state, deps.now().date()),
        *ALWAYS_ASK,
    ]

    asked = {question.key for question in fixed}
    chosen: list[Question] = []
    for question in _model_questions(deps, state):
        if question.key in asked:
            continue
        asked.add(question.key)
        chosen.append(question)

    return [*fixed, *chosen[: deps.settings.max_clarifying_questions]]


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


def _place(deps: Deps, state: DiagnosisState) -> str | None:
    """Name the position a photograph carried, if it carried one.

    Failure is silence: without a name the field is simply empty, and somebody types their
    town as they did before any of this existed.
    """
    if state.latitude is None or state.longitude is None:
        return None

    try:
        return deps.place_name(state.latitude, state.longitude)
    except Exception as exc:  # noqa: BLE001 - a place name is never worth a failed run
        logger.warning("could not name the place a photograph carried: %s", exc)
        return None


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

        place = _place(deps, state)
        return {
            "questions": select_questions(deps, state, place),
            "detected_place": place,
        }

    return select_questions_node


def _captured_from(answers) -> dict:
    """What the capture-date answer means for state.

    The question is required, so an empty answer should not arrive — the form refuses it and
    so does the service. If one does, state keeps what it had rather than being emptied:
    losing the date would silently widen the weather window to wherever today happens to be,
    which is worse than the answer somebody failed to give.
    """
    if CAPTURE_KEY not in answers:
        return {}

    given = (answers.get(CAPTURE_KEY) or "").strip()
    if not given:
        return {}

    try:
        # Midnight UTC, on the same reasoning as reading the tag in the first place: the
        # server has no idea what timezone somebody is in, and inventing one moves a date
        # across a boundary for half the world.
        return {"captured_at": datetime.fromisoformat(given).replace(tzinfo=UTC)}
    except ValueError:
        logger.warning("unusable capture date from a client: %r", given)
        return {}


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
                # How old a photograph may be before it is worth saying so. Sent rather than
                # decided here because the date is still being edited: the field is
                # prefilled and the owner may correct it, and the warning has to follow what
                # is in the field rather than what the camera happened to record.
                "stale_after_days": deps.settings.stale_photograph_days,
                # Always present, whatever its length. One candidate means every method,
                # and the owner if they said anything, named the same plant — nothing to
                # choose between, but still worth saying plainly instead of leaving the
                # pause silent about what this plant is going to be recorded as. The client
                # renders a choice only above one entry, and a plain statement at one.
                "identification": [c.model_dump() for c in state.candidates],
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

    captured = _captured_from(answers)

    chosen = given.get("species")
    if not chosen:
        return {"answers": dict(answers), **captured}

    name = chosen.get("common_name") or "Unknown"
    return {
        "answers": dict(answers),
        **captured,
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
