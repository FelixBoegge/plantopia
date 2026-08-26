"""Species identification.

Knowing the species is what makes "is this normal?" answerable — the same drooping
leaves mean different things on a peace lily and on a cactus.

**Two methods, in sequence, and the sequence is deliberate.** The vision model reports the
species *and* what each photograph shows; the organs then go to a specialist identifier,
which is markedly more accurate given them. Running the two in parallel would mean tagging
the organs in a separate call — one more model call on every diagnosis, to save a second or
two of a run that takes ninety.

**Neither method is told what the owner thinks it is.** Not the species they typed, and
not the name they gave the plant — a hint would make the two identifications agree with the
owner rather than with the evidence, and three parties agreeing because two were handed the
third's answer is not agreement.

Neither method is authoritative either. Both answers are carried as candidates; where all
of them coincide the diagnosis proceeds without asking, and where they do not the owner
settles it at the pause that already exists.
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

        # **The photographs and nothing else.**
        #
        # This used to pass the owner's name for the plant as a hint. It cannot: neither
        # the species they typed nor the name they gave it, and the name is the less
        # obvious of the two — "Kitchen basil" is a nickname that contains the answer.
        #
        # A vision model told what the owner thinks tends to agree with the owner, so
        # "both methods and the owner agree" would stop being corroboration and become an
        # echo of one claim. The whole value of a second opinion is that it was reached
        # separately, and this is the line that makes that true.
        #
        # It costs something: the identification is very likely slightly worse without the
        # hint. Worth it, because an identification that is confidently wrong *and*
        # unfalsifiable is worse than one that is honestly uncertain.
        messages = [
            SystemMessage(IDENTIFY_PLANT),
            build_image_message(
                "What species is this?",
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
                # No method produced it, and saying one did would be a lie in the field
                # that exists to make a wrong diagnosis attributable.
                "species_method": None,
                "errors": [*state.errors, f"identify_plant: {exc}"],
            }

        vision = SpeciesCandidate(
            common_name=seen.common_name,
            scientific_name=seen.scientific_name,
            confidence=seen.confidence,
            method=SpeciesMethod.VISION,
        )
        candidates, errors = _with_second_opinion(deps, state, seen, vision)
        candidates = _ranked(candidates, state.stated_species)

        # The leading candidate, which `_ranked` has just put first. The owner can change
        # it at the pause, and `gather_context` writes what they chose.
        leader = candidates[0]

        return {
            "species": SpeciesGuess(
                common_name=leader.common_name,
                scientific_name=leader.scientific_name,
                confidence=leader.confidence,
            ),
            "candidates": candidates,
            "species_method": leader.method,
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


# How sure a typed species is. Not a probability and not comparable with the two methods'
# scores — the person is not estimating a likelihood, they are telling you what their plant
# is. Written as a named constant rather than an inline number so it cannot be mistaken for
# a measurement, and set high enough that a chooser sorting by confidence still leads with
# it.
STATED_CONFIDENCE = 1.0


def _ranked(candidates: list[SpeciesCandidate], stated: str | None) -> list[SpeciesCandidate]:
    """Put the leading candidate first, and add the typed one if there is one.

    Precedence: **what the owner typed, then what both methods agree on, then the vision
    model's.** Never the highest confidence across methods, which would be arithmetic on
    scales that were never calibrated against each other.

    The owner leads because they are holding the plant and may have the label, the receipt,
    or ten years of owning it. It is a real trade: the identification prompt tells the model
    to treat a supplied name as a hint precisely because people mislabel their plants, and
    this makes that same name the default. What keeps it honest is that both methods still
    ran and both answers are still here — the disagreement is one click from being settled
    the other way, rather than being resolved quietly in either direction.
    """
    if stated:
        typed = SpeciesCandidate(
            common_name=stated,
            scientific_name=None,
            confidence=STATED_CONFIDENCE,
            method=SpeciesMethod.TYPED,
        )
        # If a method independently named the same plant, that is agreement worth saying so,
        # not a duplicate row that makes somebody choose between a thing and itself.
        rest = [other for other in candidates if not _matches_typed(stated, other)]
        return [typed, *rest]

    agreed = next((c for c in candidates if c.method is SpeciesMethod.AGREED), None)
    if agreed is not None:
        return [agreed, *[c for c in candidates if c is not agreed]]

    return candidates


def _matches_typed(stated: str, candidate: SpeciesCandidate) -> bool:
    """Whether what somebody typed names the plant this candidate names.

    Looser than the comparison between two identified candidates, and deliberately so. That
    one insists on the scientific name because the alternative is a real collision — the
    recorded fixture has two different plants both called "Mini monstera". This one has no
    such luxury: the species field is a single free-text box, and a person will type
    "basil" or "Ocimum basilicum" into it with equal cheerfulness, so the typed text is
    compared against both of a candidate's names.

    The cost of being wrong here is small in the direction it can be wrong: a false match
    hides a candidate that agreed anyway, and a missed match shows a choice between two
    spellings of the same plant. Neither produces a wrong diagnosis; a strict comparison
    would produce the second one constantly.
    """
    typed = stated.casefold().strip()
    names = {candidate.common_name.casefold()}
    if candidate.scientific_name:
        names.add(candidate.scientific_name.casefold())
    return typed in names


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
