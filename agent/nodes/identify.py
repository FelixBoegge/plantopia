"""Species identification.

Knowing the species is what makes "is this normal?" answerable — the same drooping
leaves mean different things on a peace lily and on a cactus.

**Two methods, in sequence, and the sequence is deliberate.** The vision model reports the
species *and* what each photograph shows; the organs then go to a specialist identifier,
which is markedly more accurate given them. Running the two in parallel would mean tagging
the organs in a separate call — one more model call on every diagnosis, to save a second or
two of a run that takes ninety.

Neither method is authoritative. Both answers are carried as candidates, and where they
disagree the owner settles it at the pause that already exists.
"""

import logging

from langchain_core.messages import SystemMessage

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.prompts.identify import IDENTIFY_PLANT
from agent.schemas import (
    ImageOrgan,
    SpeciesCandidate,
    SpeciesGuess,
    SpeciesMethod,
    VisionIdentification,
)
from agent.state import DiagnosisState
from agent.structured import StructuredOutputFailed, invoke_structured
from agent.vision import build_image_message

logger = logging.getLogger(__name__)

UNKNOWN_SPECIES = SpeciesGuess(common_name="Unknown", scientific_name=None, confidence=0.0)


def make_identify_plant(deps: Deps) -> NodeFn:
    """Identify the plant, or record that it could not be identified.

    Failure is not fatal: an unknown species widens the differential and opens the
    web-search escalation gate rather than stopping the diagnosis. That applies to both
    methods independently — one of them answering is better than neither, and neither
    answering is where this node started.
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
            seen = invoke_structured(deps.vision_model, VisionIdentification, messages)
        except StructuredOutputFailed as exc:
            logger.warning("identify_plant failed: %s", exc)
            # The specialist is not asked either. It takes the organs as input and there
            # are none — and a diagnosis whose vision call just failed has larger problems
            # than a missing second opinion.
            return {
                "species": UNKNOWN_SPECIES,
                "errors": [*state.errors, f"identify_plant: {exc}"],
            }

        vision = SpeciesCandidate(
            common_name=seen.common_name,
            scientific_name=seen.scientific_name,
            confidence=seen.confidence,
            method=SpeciesMethod.VISION,
        )
        candidates, errors = _with_second_opinion(deps, state, seen, vision)

        # The species stays the vision model's until somebody says otherwise. Not the
        # highest-confidence candidate: the two methods report confidence on scales that
        # were never calibrated against each other, so preferring one number over the other
        # would be arithmetic on incomparable quantities. The owner decides at the pause,
        # and `gather_context` writes what they chose.
        return {
            "species": seen.species(),
            "candidates": candidates,
            **({"errors": [*state.errors, *errors]} if errors else {}),
        }

    return identify_plant


def _with_second_opinion(
    deps: Deps,
    state: DiagnosisState,
    seen: VisionIdentification,
    vision: SpeciesCandidate,
) -> tuple[list[SpeciesCandidate], list[str]]:
    """Ask the specialist too, and merge what comes back.

    Returns the candidates and anything worth recording against the run.

    **Never raises, and the guard covers the call as well as the preparation.** The adapter
    already answers every failure with an empty list, so nothing here should be able to
    throw — which is the argument for leaving it uncovered, and it is not good enough. This
    is one of two model-independent identifications inside a diagnosis somebody paid for;
    trusting another module's guarantee absolutely, at the cost of the whole run if it does
    not hold, is a bad trade for one indentation level.
    """
    try:
        photographs = [
            (_bytes_of(deps, image.ref), seen.organ_for(index))
            for index, image in enumerate(state.images)
        ]
        found = deps.identify_species(photographs)
    except Exception as exc:  # noqa: BLE001 - a second opinion is never worth a failure
        logger.warning("the second identification could not be made: %s", exc)
        return [vision], [f"identify_plant: second opinion skipped ({exc})"]

    if not found:
        # Indistinguishable here from "no key configured", and deliberately so: the node
        # does the same thing either way, and the adapter has already logged which.
        return [vision], []

    return _merged(vision, found), []


def _bytes_of(deps: Deps, ref: str) -> bytes:
    data = deps.blobs.get(deps.user_id, ref)
    if data is None:
        raise ValueError(f"photograph {ref} is not in the store")
    return data


def _merged(vision: SpeciesCandidate, found: list[SpeciesCandidate]) -> list[SpeciesCandidate]:
    """One list, with agreement collapsed into a single candidate that says so.

    Two methods naming the same plant is the strongest signal available here, and showing
    it twice would present it as two things to choose between rather than as one thing
    twice confirmed.

    Compared on the scientific name where both have one, because that is what makes two
    spellings comparable — the recorded fixture has two different plants sharing the common
    name "Mini monstera", which is exactly the collision a common-name comparison would get
    wrong.
    """
    for candidate in found:
        if _same_plant(vision, candidate):
            agreed = SpeciesCandidate(
                common_name=candidate.common_name,
                scientific_name=candidate.scientific_name or vision.scientific_name,
                # The higher of the two. Both methods identifying the same plant is not
                # weaker evidence than either alone, which averaging them would imply.
                confidence=max(vision.confidence, candidate.confidence),
                method=SpeciesMethod.AGREED,
            )
            rest = [other for other in found if other is not candidate]
            return [agreed, *rest]

    return [vision, *found]


def _same_plant(one: SpeciesCandidate, other: SpeciesCandidate) -> bool:
    if one.scientific_name and other.scientific_name:
        return one.scientific_name.casefold() == other.scientific_name.casefold()
    return one.common_name.casefold() == other.common_name.casefold()


__all__ = ["ImageOrgan", "UNKNOWN_SPECIES", "make_identify_plant"]
