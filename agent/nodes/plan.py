"""Contagion assessment and treatment planning."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.prompts.plan import BUILD_ROADMAP
from agent.schemas import ContagionAssessment, Roadmap
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured
from core.guards import scan_for_injection, wrap_untrusted
from tools.knowledge import treatment_notes

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

        messages = [
            SystemMessage(BUILD_ROADMAP),
            HumanMessage(_build_brief(state, _treatment(deps, differential))),
        ]
        try:
            roadmap = invoke_structured(deps.chat_model, Roadmap, messages)
        except StructuredOutputFailed as exc:
            logger.warning("build_roadmap failed: %s", exc)
            return {"roadmap": None, "errors": [*state.errors, f"build_roadmap: {exc}"]}

        return {"roadmap": roadmap}

    return build_roadmap


def _build_brief(state: DiagnosisState, treatment: list) -> str:
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

    # Last, and deliberately after the differential it belongs to: the steps are
    # written from this, and it reads as guidance about candidates already named
    # rather than as evidence for naming them.
    if treatment:
        parts.append(_format_treatment(treatment))

    return "\n\n".join(parts)


def _treatment(deps: Deps, differential) -> list:
    """What the corpus says to do about each candidate.

    Degrades to nothing. A plan written from the differential alone is what this node
    did for months, which is worse than one that read the corpus and far better than
    none — so a store that cannot be reached costs the plan its grounding, never the
    owner their roadmap.
    """
    try:
        return treatment_notes(deps.retriever, [c.disorder_id for c in differential.candidates])
    except Exception:  # pragma: no cover - a plan must survive an unreachable corpus
        logger.exception("could not read treatment guidance; planning without it")
        return []


def _format_treatment(passages: list) -> str:
    """Fence it as untrusted data (spec §13.2).

    The same rule `diagnose` applies to the symptom passages, and it holds here for the
    same reason: retrieved text is data, never instruction. That this project wrote the
    corpus itself does not exempt it — the guard is about what the channel is, not
    about who is trusted on it.
    """
    blocks = []
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
    return "What the reference material says to do:\n\n" + "\n\n".join(blocks)
