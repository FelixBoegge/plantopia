"""Intake nodes: is this a plant, and are the photos good enough?"""

import logging
from collections.abc import Callable

from langchain_core.messages import SystemMessage

from agent.deps import Deps
from agent.prompts.intake import GUARD_INPUT, QUALITY_CHECK
from agent.schemas import ImageQuality, PlantCheck
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured
from agent.vision import build_image_message

logger = logging.getLogger(__name__)

NodeFn = Callable[[DiagnosisState], dict]


def make_guard_input(deps: Deps) -> NodeFn:
    """Reject anything that is not plant material.

    This closes the path where a user uploads a photo of a person and receives
    diagnostic-sounding advice from a system with no medical competence. On model
    failure it rejects rather than proceeding: failing closed is the right default
    for a guard.
    """

    def guard_input(state: DiagnosisState) -> dict:
        messages = [
            SystemMessage(GUARD_INPUT),
            build_image_message(
                "Is this plant material?",
                state.images,
                blobs=deps.blobs,
                user_id=deps.user_id,
            ),
        ]
        try:
            check = invoke_structured(deps.gate_model, PlantCheck, messages)
        except StructuredOutputFailed as exc:
            logger.warning("guard_input could not run: %s", exc)
            return {
                "rejected": True,
                "rejection_reason": (
                    "I could not check this image right now. Please try again in a moment."
                ),
                "errors": [*state.errors, f"guard_input: {exc}"],
            }

        if not check.is_plant:
            return {
                "rejected": True,
                "rejection_reason": (
                    f"This looks like {check.what_it_is}, not a plant. "
                    "Plantopia only diagnoses plants — please upload a photo of the plant "
                    "you are concerned about."
                ),
            }

        return {"rejected": False}

    return guard_input


def make_quality_check(deps: Deps) -> NodeFn:
    """Judge whether the photos can support a diagnosis.

    Unlike the guard, this fails open: a quality check that cannot run must not block
    a diagnosis the model could otherwise make.
    """

    def quality_check(state: DiagnosisState) -> dict:
        messages = [
            SystemMessage(QUALITY_CHECK),
            build_image_message(
                "Are these usable for diagnosis?",
                state.images,
                blobs=deps.blobs,
                user_id=deps.user_id,
            ),
        ]
        try:
            quality = invoke_structured(deps.gate_model, ImageQuality, messages)
        except StructuredOutputFailed as exc:
            logger.warning("quality_check could not run: %s", exc)
            return {
                "quality": ImageQuality(usable=True, problem=None, guidance=None),
                "errors": [*state.errors, f"quality_check: {exc}"],
            }

        return {"quality": quality}

    return quality_check
