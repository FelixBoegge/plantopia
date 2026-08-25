"""Contagion assessment and treatment planning."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.prompts.plan import BUILD_ROADMAP
from agent.schemas import ContagionAssessment, Roadmap
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured

logger = logging.getLogger(__name__)

NO_RISK = ContagionAssessment(
    at_risk=False,
    advice="This problem does not spread to other plants, so no quarantine is needed.",
)


def make_check_contagion(deps: Deps) -> NodeFn:
    """Decide whether nearby plants are at risk.

    Deterministic by design. The rule — transmissible disorder plus other plants in
    the journal — is simple enough that a model call would only add latency and
    another way to be wrong. This is also the first place the app's long-term memory
    changes the advice the user receives.
    """

    def check_contagion(state: DiagnosisState) -> dict:
        primary = state.differential.primary if state.differential else None
        if primary is None or not primary.transmissible:
            return {"contagion": NO_RISK}

        others = [p for p in deps.plants.list_all(deps.user_id) if p.id != state.plant_id]
        if not others:
            return {
                "contagion": ContagionAssessment(
                    at_risk=False,
                    advice=(
                        f"{primary.name} can spread between plants, but you have no other "
                        "plants recorded. Keep any new plants away from this one until it "
                        "has recovered."
                    ),
                )
            }

        names = ", ".join(p.name for p in others)
        return {
            "contagion": ContagionAssessment(
                at_risk=True,
                advice=(
                    f"{primary.name} spreads between plants. Move this plant away from "
                    f"{names} today, and check them for the same symptoms. Wash your hands "
                    "and any tools between plants."
                ),
            )
        }

    return check_contagion


def make_build_roadmap(deps: Deps) -> NodeFn:
    """Turn the diagnosis into an IPM-ordered treatment plan.

    If the model cannot produce a schema-valid, correctly ordered roadmap, the node
    leaves it unset. A fabricated treatment plan would be worse than showing the
    diagnosis and admitting the plan is unavailable.
    """

    def build_roadmap(state: DiagnosisState) -> dict:
        differential = state.differential
        if differential is None or differential.is_healthy:
            return {"roadmap": None}

        messages = [SystemMessage(BUILD_ROADMAP), HumanMessage(_build_brief(state))]
        try:
            roadmap = invoke_structured(deps.chat_model, Roadmap, messages)
        except StructuredOutputFailed as exc:
            logger.warning("build_roadmap failed: %s", exc)
            return {"roadmap": None, "errors": [*state.errors, f"build_roadmap: {exc}"]}

        return {"roadmap": roadmap}

    return build_roadmap


def _build_brief(state: DiagnosisState) -> str:
    differential = state.differential
    assert differential is not None  # guarded by the caller

    candidate_lines = "\n".join(
        f"- {c.name} ({c.probability:.0%}, severity {c.severity.value}): supported by "
        f"{'; '.join(c.supporting_evidence)}"
        for c in differential.candidates
    )

    parts = [
        f"Plant: {state.species_name or 'unidentified'} ({state.location_kind})",
        f"Differential:\n{candidate_lines}",
        f"Reasoning: {differential.reasoning}",
    ]

    if state.low_confidence:
        parts.append(
            "The diagnosis is low confidence. Begin with reversible cultural changes and "
            "with the distinguishing tests, rather than committing to one treatment."
        )

    if state.contagion and state.contagion.at_risk:
        parts.append(f"Contagion: {state.contagion.advice}")

    if state.answers:
        answers = "\n".join(f"- {k}: {v}" for k, v in state.answers.items())
        parts.append(f"What the owner told us:\n{answers}")

    return "\n\n".join(parts)
