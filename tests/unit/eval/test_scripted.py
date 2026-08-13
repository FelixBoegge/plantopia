"""Unit tests for the schema-dispatching evaluation model."""

from agent.schemas import ImageQuality, PlantCheck, SpeciesGuess, SymptomSet
from eval.cases import GoldenCase
from eval.scripted import SchemaDispatchModel, case_models


def _case() -> GoldenCase:
    return GoldenCase.model_validate(
        {
            "id": "t",
            "category": "watering",
            "plant": {"name": "Test", "species": "Ficus elastica"},
            "species_confidence": 0.9,
            "symptoms": {
                "overall_vigor": "declining",
                "soil_condition": "wet",
                "symptoms": [
                    {
                        "description": "yellowing lower leaves",
                        "position": "lower_leaves",
                        "severity": "act_this_week",
                    }
                ],
            },
            "ground_truth": "overwatering",
        }
    )


def test_dispatch_is_independent_of_call_order():
    """route_after_quality branches, so a positional queue desynchronises (spec §3.3)."""
    model = SchemaDispatchModel(case=_case())

    symptoms = model.with_structured_output(SymptomSet).invoke("prompt")
    species = model.with_structured_output(SpeciesGuess).invoke("prompt")

    assert species.common_name == "Ficus elastica"
    assert symptoms.symptoms[0].position.value == "lower_leaves"


def test_the_same_schema_can_be_requested_twice():
    """A re-check may identify a plant a second time; a queue would be exhausted."""
    model = SchemaDispatchModel(case=_case())

    first = model.with_structured_output(SpeciesGuess).invoke("p")
    second = model.with_structured_output(SpeciesGuess).invoke("p")

    assert first == second


def test_the_guards_pass():
    model = SchemaDispatchModel(case=_case())

    assert model.with_structured_output(PlantCheck).invoke("p").is_plant is True
    assert model.with_structured_output(ImageQuality).invoke("p").usable is True


def test_species_confidence_comes_from_the_case():
    model = SchemaDispatchModel(case=_case())

    assert model.with_structured_output(SpeciesGuess).invoke("p").confidence == 0.9


def test_a_case_without_a_species_still_identifies():
    """A blank species must not produce an empty common_name, which SpeciesGuess rejects."""
    raw = _case().model_dump()
    raw["plant"]["species"] = None
    model = SchemaDispatchModel(case=GoldenCase.model_validate(raw))

    guess = model.with_structured_output(SpeciesGuess).invoke("p")
    assert guess.common_name
    assert guess.confidence == 0.0


def test_an_unknown_schema_raises():
    """Silence here would mean a node quietly received nothing at all."""
    from pydantic import BaseModel

    class Unknown(BaseModel):
        pass

    model = SchemaDispatchModel(case=_case())

    try:
        model.with_structured_output(Unknown).invoke("p")
    except ValueError as exc:
        assert "Unknown" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_case_models_returns_a_gate_and_a_vision_tier():
    gate, vision = case_models(_case())

    assert gate.with_structured_output(PlantCheck).invoke("p").is_plant is True
    assert vision.with_structured_output(SpeciesGuess).invoke("p").common_name == "Ficus elastica"
