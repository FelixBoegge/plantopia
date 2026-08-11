"""Re-check nodes: judging progress against a prior diagnosis and revising the plan.

Both nodes are only ever reached for a known plant (routed there because
``state.plant_id`` was already set when the run started — see
``agent/diagnosis_graph.py``), so neither re-checks that precondition beyond the
assertion below.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.prompts.recheck import COMPARE_PROGRESS, REVISE_ROADMAP
from agent.schemas import ProgressVerdict, Roadmap
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured
from data.repositories.diagnoses import DiagnosisRecord
from data.repositories.roadmap import RoadmapStepRecord

logger = logging.getLogger(__name__)

_NO_PRIOR_DIAGNOSIS = ProgressVerdict(
    verdict="new_problem", reasoning="No prior diagnosis is on record for this plant."
)
_COMPARISON_FAILED = ProgressVerdict(
    verdict="new_problem",
    reasoning="The comparison could not be completed; treating this as a new problem.",
)


def make_compare_progress(deps: Deps) -> NodeFn:
    """Judge progress against the prior diagnosis and roadmap completion."""

    def compare_progress(state: DiagnosisState) -> dict:
        assert state.plant_id is not None  # routed here only for a known plant
        prior = deps.diagnoses.latest_for_plant(state.plant_id)
        if prior is None:
            return {"verdict": _NO_PRIOR_DIAGNOSIS}

        steps = deps.roadmap.list_for_plant(state.plant_id)
        messages = [
            SystemMessage(COMPARE_PROGRESS),
            HumanMessage(_build_comparison(state, prior, steps)),
        ]
        try:
            verdict = invoke_structured(deps.chat_model, ProgressVerdict, messages)
        except StructuredOutputFailed as exc:
            logger.warning("compare_progress failed: %s", exc)
            return {
                "verdict": _COMPARISON_FAILED,
                "errors": [*state.errors, f"compare_progress: {exc}"],
            }

        return {"verdict": verdict}

    return compare_progress


def make_revise_roadmap(deps: Deps) -> NodeFn:
    """Taper or escalate the roadmap for an improving/static verdict, without
    re-running ``diagnose``. Carries the prior differential forward unchanged."""

    def revise_roadmap(state: DiagnosisState) -> dict:
        assert state.plant_id is not None and state.verdict is not None
        prior = deps.diagnoses.latest_for_plant(state.plant_id)
        assert prior is not None  # compare_progress already confirmed one exists

        steps = deps.roadmap.list_for_plant(state.plant_id)
        messages = [
            SystemMessage(REVISE_ROADMAP),
            HumanMessage(_build_revision_brief(state, steps)),
        ]
        try:
            roadmap = invoke_structured(deps.chat_model, Roadmap, messages)
        except StructuredOutputFailed as exc:
            logger.warning("revise_roadmap failed: %s", exc)
            return {
                "differential": prior.differential,
                "roadmap": None,
                "errors": [*state.errors, f"revise_roadmap: {exc}"],
            }

        return {"differential": prior.differential, "roadmap": roadmap}

    return revise_roadmap


def _format_steps(steps: list[RoadmapStepRecord]) -> str:
    lines = "\n".join(f"- {s.action} — {s.status}" for s in steps)
    return lines or "No prior roadmap steps were recorded."


def _build_comparison(
    state: DiagnosisState, prior: DiagnosisRecord, steps: list[RoadmapStepRecord]
) -> str:
    if prior.differential.is_healthy:
        candidate_lines = "The plant was previously assessed as healthy."
    else:
        candidate_lines = "\n".join(
            f"- {c.name} ({c.probability:.0%})" for c in prior.differential.candidates
        )

    symptom_lines = (
        "\n".join(f"- {s.description} ({s.position.value})" for s in state.symptoms.symptoms)
        if state.symptoms
        else "Symptoms could not be extracted from today's photographs."
    )

    return (
        f"Prior differential:\n{candidate_lines}\n\n"
        f"Prior roadmap and completion status:\n{_format_steps(steps)}\n\n"
        f"Today's symptoms:\n{symptom_lines}"
    )


def _build_revision_brief(state: DiagnosisState, steps: list[RoadmapStepRecord]) -> str:
    assert state.verdict is not None
    return (
        f"Verdict: {state.verdict.verdict}\n"
        f"Verdict reasoning: {state.verdict.reasoning}\n\n"
        f"Prior roadmap:\n{_format_steps(steps)}"
    )
