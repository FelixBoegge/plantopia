"""Species identification.

Knowing the species is what makes "is this normal?" answerable — the same drooping
leaves mean different things on a peace lily and on a cactus.
"""

import logging

from langchain_core.messages import SystemMessage

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.prompts.identify import IDENTIFY_PLANT
from agent.schemas import SpeciesGuess
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured
from agent.vision import build_image_message

logger = logging.getLogger(__name__)

UNKNOWN_SPECIES = SpeciesGuess(common_name="Unknown", scientific_name=None, confidence=0.0)


def make_identify_plant(deps: Deps) -> NodeFn:
    """Identify the plant, or record that it could not be identified.

    Failure is not fatal: an unknown species widens the differential and opens the
    web-search escalation gate rather than stopping the diagnosis.
    """

    def identify_plant(state: DiagnosisState) -> dict:
        if state.species is not None:
            return {}

        hint = f'The user calls this plant "{state.plant_name}".'
        messages = [
            SystemMessage(IDENTIFY_PLANT),
            build_image_message(
                f"{hint}\n\nWhat species is this?",
                state.images,
                blobs=deps.blobs,
                user_id=deps.user_id,
            ),
        ]
        try:
            guess = invoke_structured(deps.vision_model, SpeciesGuess, messages)
        except StructuredOutputFailed as exc:
            logger.warning("identify_plant failed: %s", exc)
            return {
                "species": UNKNOWN_SPECIES,
                "errors": [*state.errors, f"identify_plant: {exc}"],
            }

        return {"species": guess}

    return identify_plant
