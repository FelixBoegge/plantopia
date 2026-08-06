"""Tests for structured symptom extraction."""

from agent.nodes.symptoms import make_assess_symptoms
from agent.schemas import Severity, SpeciesGuess, Symptom, SymptomPosition, SymptomSet
from agent.state import DiagnosisState
from tests.fakes.chat_models import FailingChatModel, ScriptedStructuredModel


def _symptoms() -> SymptomSet:
    return SymptomSet(
        symptoms=[
            Symptom(
                description="Yellowing between the veins",
                position=SymptomPosition.INTERVEINAL,
                severity=Severity.ACT_THIS_WEEK,
            )
        ],
        soil_condition="dry on top",
        overall_vigor="declining",
    )


def _state(images, **overrides) -> DiagnosisState:
    return DiagnosisState(images=images, plant_name="Basil", location_kind="indoor", **overrides)


def test_records_the_symptom_set(make_deps, sample_images):
    deps = make_deps(vision_model=ScriptedStructuredModel([_symptoms()]))
    result = make_assess_symptoms(deps)(_state(sample_images))
    assert result["symptoms"] == _symptoms()


def test_position_survives_extraction(make_deps, sample_images):
    deps = make_deps(vision_model=ScriptedStructuredModel([_symptoms()]))
    result = make_assess_symptoms(deps)(_state(sample_images))
    assert result["symptoms"].symptoms[0].position is SymptomPosition.INTERVEINAL


def test_species_is_included_in_the_prompt_when_known(make_deps, sample_images):
    model = ScriptedStructuredModel([_symptoms()])
    deps = make_deps(vision_model=model)
    state = _state(
        sample_images,
        species=SpeciesGuess(common_name="Basil", scientific_name=None, confidence=0.9),
    )
    make_assess_symptoms(deps)(state)
    assert "Basil" in model.prompts[0][-1].content[0]["text"]


def test_user_notes_are_included_in_the_prompt(make_deps, sample_images):
    model = ScriptedStructuredModel([_symptoms()])
    deps = make_deps(vision_model=model)
    state = _state(sample_images, user_notes="started three days after I repotted it")
    make_assess_symptoms(deps)(state)
    assert "repotted" in model.prompts[0][-1].content[0]["text"]


def test_failure_records_an_error_and_no_symptoms(make_deps, sample_images):
    deps = make_deps(vision_model=FailingChatModel(RuntimeError("api down")))
    result = make_assess_symptoms(deps)(_state(sample_images))
    assert result["symptoms"] is None
    assert result["errors"]
