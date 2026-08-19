"""Run one golden case through the real diagnosis graph.

Only the gate and vision tiers are scripted (``eval/scripted.py``). The reasoning
model, the retriever, the corpus, the graph, and the interrupt are all real — this
measures retrieval and differential reasoning, which is exactly what the Ragas
metrics can see (spec §3.1).
"""

import logging
from dataclasses import dataclass, field

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from agent.deps import Deps
from agent.schemas import ImageRef, Question
from agent.state import DiagnosisState
from core.cost import UsageCollector, UsageSnapshot
from eval.cases import GoldenCase

logger = logging.getLogger(__name__)

# ``DiagnosisState.images`` requires at least one entry (spec-enforced by the real
# schema, not a harness choice), and ``guard_input``/``quality_check`` both build a
# vision message from ``state.images`` before ever consulting a model. Golden cases
# are text, so this one-pixel placeholder stands in for a photograph the case never
# had; the gate and vision tiers are scripted to pass it unconditionally either way.
_PLACEHOLDER_IMAGE = ImageRef(ref="golden-case", media_type="image/png", data_b64="aGVsbG8=")

# ``questions_asked`` records the *complete* interrupt payload — watering and
# drainage (``agent.nodes.context.ALWAYS_ASK_KEYS``), the conditional location
# question, and whatever the model chose. It deliberately does not filter out the
# deterministic ones here: this list is written verbatim into a committed,
# human-auditable results JSON, and filtering at capture time would permanently
# lose the fact that the owner was asked (and answered) watering and drainage —
# nothing downstream could recover that from the file. The deterministic keys still
# do not count as drift, because they never vary between runs of the *same* case
# and only the model-chosen questions are a variance source distinct from
# diagnostic instability (spec §3.4) — but that subtraction belongs in the drift
# metric, computed from the same stable, importable production constants, not
# baked into the record.


@dataclass(frozen=True, slots=True)
class CaseRun:
    """What one pass over one case produced."""

    case_id: str
    ground_truth: str
    category: str
    candidates: list[str]
    reasoning: str
    contexts: list[str]
    questions_asked: list[str]
    situation: str
    usage: UsageSnapshot | None
    error: str | None = None

    # The subset of ``contexts`` that similarity search actually ranked, as opposed to
    # the sections fetched by id — the look-alikes attached to each candidate, and the
    # documents ``hypothesise`` named. Both arrive with a score of 0.0 because nothing
    # ranked them, which is what separates the two here.
    #
    # Kept apart for context precision, which asks what fraction of retrieved material
    # was relevant. That is a question about ranking, and material deliberately fetched
    # has no ranking to judge: a look-alikes section describes *other* disorders by
    # design, so scoring it as a retrieval hit would mark down a mechanism working
    # exactly as intended. Recall and faithfulness still see everything the model saw.
    ranked_contexts: list[str] = field(default_factory=list)


def _answers_for(case: GoldenCase, questions: list[Question]) -> dict[str, str]:
    """Answer every question asked, falling back for ones the case did not foresee."""
    return {
        question.key: case.answers.get(question.key, case.default_answer) for question in questions
    }


def _situation(case: GoldenCase, answers: dict[str, str]) -> str:
    """The situation as the plant owner actually presented it: symptoms plus answers.

    Feeds ``eval.ragas_metrics.to_ragas_rows`` as ``user_input``. It must vary
    between cases — the defect this replaces was a single sentence identical for
    every one of the 28 golden cases, which made ``answer_relevancy`` measure the
    harness's placeholder question rather than the agent's response.
    """
    descriptions = "; ".join(symptom.description for symptom in case.symptoms.symptoms)
    situation = f"My plant has these symptoms: {descriptions}."
    if answers:
        details = "; ".join(f"{key}: {value}" for key, value in answers.items())
        situation += f" Additional details: {details}."
    return situation


def run_case(case: GoldenCase, *, deps: Deps, graph: CompiledStateGraph, thread_id: str) -> CaseRun:
    """Run one case end to end. Never raises — a failure becomes a recorded row.

    A single bad case must not abort a thirty-case run (spec §5), so every
    exception is caught and reported as data.
    """
    collector = UsageCollector()
    config = {
        "configurable": {"thread_id": thread_id, "usage_collector": collector},
        "callbacks": [collector],
    }

    def _failed(message: str, situation: str) -> CaseRun:
        return CaseRun(
            case_id=case.id,
            ground_truth=case.ground_truth,
            category=case.category,
            candidates=[],
            reasoning="",
            contexts=[],
            questions_asked=[],
            situation=situation,
            usage=collector.snapshot(),
            error=message,
        )

    try:
        state = DiagnosisState(
            images=[_PLACEHOLDER_IMAGE],
            plant_name=case.plant.name,
            location_kind=case.plant.location_kind,
            location_text=case.plant.location_text,
            user_notes=None,
        )
        started = graph.invoke(state, config)

        questions_asked: list[str] = []
        answers_given: dict[str, str] = {}
        interrupts = started.get("__interrupt__") or []
        if interrupts:
            questions = [Question.model_validate(q) for q in interrupts[0].value["questions"]]
            questions_asked = [question.key for question in questions]
            answers_given = _answers_for(case, questions)
            result = graph.invoke(Command(resume=answers_given), config)
        else:
            result = started

        situation = _situation(case, answers_given)
        retrieved = result.get("retrieved") or []

        differential = result.get("differential")
        if differential is None:
            return _failed("the run produced no differential", situation)

        return CaseRun(
            case_id=case.id,
            ground_truth=case.ground_truth,
            category=case.category,
            candidates=[candidate.disorder_id for candidate in differential.candidates],
            reasoning=differential.reasoning,
            contexts=[passage.text for passage in retrieved],
            ranked_contexts=[passage.text for passage in retrieved if passage.score > 0],
            questions_asked=questions_asked,
            situation=situation,
            usage=collector.snapshot(),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 — a failed case is data, not a crash
        logger.warning("case %s failed: %s", case.id, exc)
        return _failed(f"{type(exc).__name__}: {exc}", _situation(case, {}))
