"""A scripted model that answers by schema, not by call order.

Deliberately unlike ``tests/fakes/chat_models.py``'s ``ScriptedStructuredModel``,
which replays a positional queue. ``route_after_quality`` branches — a re-check of
an unidentified plant calls ``identify_plant``, a fresh diagnosis may not — and a
positional queue desynchronises on the branch, returning a ``SymptomSet`` where a
``SpeciesGuess`` was asked for. Dispatching on the requested schema is
order-independent and re-entrant (spec §3.3).

Keeping this here rather than importing the test fake also keeps the dependency
direction right: nothing outside ``tests/`` should import from it.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from agent.schemas import (
    ImageQuality,
    PlantCheck,
    SpeciesGuess,
    SymptomSet,
    VisionIdentification,
)
from eval.cases import GoldenCase


def _response_for(schema: Any, case: GoldenCase) -> BaseModel:
    """The canned object a node asking for ``schema`` should receive."""
    if schema is PlantCheck:
        return PlantCheck(is_plant=True, what_it_is=f"a {case.plant.name}")
    if schema is ImageQuality:
        return ImageQuality(usable=True, problem=None, guidance=None)
    if schema is SpeciesGuess or schema is VisionIdentification:
        # An unidentified plant is a real case (a re-check routes through
        # identify_plant precisely to fix one), but common_name has min_length=1,
        # so the unknown case is expressed as zero confidence rather than an
        # empty string the schema would reject.
        #
        # Both schemas answer from the same two fields, so the species a case is scored
        # against is identical either way. ``identify_plant`` asks for the richer one; the
        # organs it also carries are left empty, because the harness never reaches the
        # identification service — see ``organs`` below.
        name = case.plant.species or "Unidentified plant"
        confidence = case.species_confidence if case.plant.species else 0.0

        if schema is SpeciesGuess:
            return SpeciesGuess(common_name=name, scientific_name=None, confidence=confidence)

        # No organs. The harness's ``Deps`` binds an identifier that returns nothing, so
        # organs would be tagged and then thrown away — and a golden case supplies its
        # symptoms as text, so there is frequently no photograph to have an organ.
        return VisionIdentification(
            common_name=name, scientific_name=None, confidence=confidence, organs=[]
        )
    if schema is SymptomSet:
        return case.symptoms
    raise ValueError(
        f"no scripted response for schema {getattr(schema, '__name__', schema)!r}. "
        "The evaluation harness only scripts the gate and vision tiers; the "
        "reasoning tier must be a real model."
    )


class SchemaDispatchModel(BaseChatModel):
    """Answers ``with_structured_output`` from a golden case, keyed by schema."""

    case: GoldenCase

    @property
    def _llm_type(self) -> str:
        return "schema-dispatch"

    def _generate(self, messages: list, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("use with_structured_output")

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        case = self.case
        return RunnableLambda(lambda _prompt: _response_for(schema, case))


def case_models(case: GoldenCase) -> tuple[BaseChatModel, BaseChatModel]:
    """The ``(gate, vision)`` tiers for one case.

    Two instances rather than one shared: ``Deps`` holds the tiers separately, and
    keeping them distinct means a future change to one cannot silently affect the
    other.
    """
    return SchemaDispatchModel(case=case), SchemaDispatchModel(case=case)
