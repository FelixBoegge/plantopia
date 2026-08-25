"""Structured symptom extraction.

Position is extracted explicitly because it carries most of the diagnostic signal.
A classifier that returns "yellowing" has discarded the information that separates
a magnesium deficiency from overwatering.
"""

import logging

from langchain_core.messages import SystemMessage

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.prompts.symptoms import ASSESS_SYMPTOMS
from agent.schemas import SymptomSet
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured
from agent.vision import build_image_message

logger = logging.getLogger(__name__)


def make_assess_symptoms(deps: Deps) -> NodeFn:
    """Extract a structured symptom set from the photographs."""

    def assess_symptoms(state: DiagnosisState) -> dict:
        parts = ["Describe the visible symptoms."]
        if state.species_name:
            parts.append(f"The plant appears to be {state.species_name}.")
        if state.user_notes:
            parts.append(f"The owner adds: {state.user_notes}")

        messages = [
            SystemMessage(ASSESS_SYMPTOMS),
            build_image_message(
                "\n\n".join(parts),
                state.images,
                blobs=deps.blobs,
                user_id=deps.user_id,
            ),
        ]
        try:
            symptoms = invoke_structured(deps.vision_model, SymptomSet, messages)
        except StructuredOutputFailed as exc:
            logger.warning("assess_symptoms failed: %s", exc)
            return {"symptoms": None, "errors": [*state.errors, f"assess_symptoms: {exc}"]}

        return {"symptoms": symptoms}

    return assess_symptoms
