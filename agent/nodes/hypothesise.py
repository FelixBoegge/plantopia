"""Name the disorders worth reading about, before retrieving anything.

Similarity search answers "which corpus text resembles this description", which is
not the same question as "what could be wrong with this plant". Measured against the
golden set, the correct document sat at rank 16, 17 and 21 of 43 for three of the six
nutrient cases: no reordering of six results reaches it, because the owner's words
("faded to a flat, dull yellow, no green left in them at all") and the corpus's
("uniform pale green or yellow, veins included") are not near neighbours.

The model's own knowledge is better at this than the retriever is. The evidence is a
case the pipeline gets right while retrieval buries the document at rank 35 —
``mealybugs``, diagnosed correctly with its reference material absent. So this node
asks the model to *name* candidates from a supplied list of ids, and ``enrich`` then
fetches those documents directly. Rank stops mattering once you can look something up
by name.

This is a shortlist for reading, never a conclusion. Nothing here writes to
``differential``; the diagnose node still has to argue from the retrieved text, and
is free to reject every hypothesis this node offered.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.prompts.hypothesise import HYPOTHESISE
from agent.schemas import Hypotheses
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured

logger = logging.getLogger(__name__)


def _describe(state: DiagnosisState, known: tuple[str, ...]) -> str:
    """The case as the model needs to see it, plus the ids it may choose from."""
    lines = [f"Species: {state.species_name or 'unidentified'}"]
    lines.append(f"Setting: {state.location_kind}")

    if state.symptoms is not None:
        observed = "\n".join(
            f"- {symptom.description} (on {symptom.position.value.replace('_', ' ')})"
            for symptom in state.symptoms.symptoms
        )
        lines.append(f"Symptoms:\n{observed}")
        lines.append(f"Soil surface: {state.symptoms.soil_condition or 'not visible'}")
        lines.append(f"Overall vigour: {state.symptoms.overall_vigor}")

    if state.answers:
        answered = "\n".join(f"- {key}: {value}" for key, value in state.answers.items())
        lines.append(f"How the owner cares for it:\n{answered}")

    if state.user_notes:
        lines.append(f"Owner's notes: {state.user_notes}")

    lines.append("Disorders in the reference library:\n" + "\n".join(f"- {i}" for i in known))
    return "\n\n".join(lines)


def make_hypothesise(deps: Deps) -> NodeFn:
    """Shortlist disorders to read about. Never fatal — retrieval still runs without it."""

    def hypothesise(state: DiagnosisState) -> dict:
        if state.symptoms is None:
            logger.info("nothing to hypothesise from: no symptoms were extracted")
            return {}

        known = deps.retriever.known_doc_ids()
        messages = [
            SystemMessage(HYPOTHESISE),
            HumanMessage(_describe(state, known)),
        ]
        try:
            result = invoke_structured(deps.chat_model, Hypotheses, messages)
        except StructuredOutputFailed as exc:
            # A failure here costs precision, not the diagnosis: enrich falls back to
            # similarity search alone, which is what the pipeline did before this node
            # existed.
            logger.warning("hypothesise failed: %s", exc)
            return {"errors": [*state.errors, f"hypothesise: {exc}"]}

        # Ids the model invented are dropped rather than fetched. sections_for would
        # skip them harmlessly, but a model naming disorders that do not exist is worth
        # seeing in the log rather than silently absorbing.
        valid = [doc_id for doc_id in result.doc_ids if doc_id in set(known)]
        invented = [doc_id for doc_id in result.doc_ids if doc_id not in set(known)]
        if invented:
            logger.warning("hypothesise named %d unknown disorder(s): %s", len(invented), invented)

        logger.info("hypothesised %s — %s", valid, result.reasoning)
        return {"hypotheses": valid, "tools_used": [*state.tools_used, "hypothesise"]}

    return hypothesise
