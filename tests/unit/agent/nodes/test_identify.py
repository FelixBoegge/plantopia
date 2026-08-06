"""Tests for species identification."""

from agent.nodes.identify import make_identify_plant
from agent.schemas import SpeciesGuess
from agent.state import DiagnosisState
from tests.fakes.chat_models import FailingChatModel, ScriptedStructuredModel


def _state(images, **overrides) -> DiagnosisState:
    return DiagnosisState(images=images, plant_name="My plant", location_kind="indoor", **overrides)


def test_records_the_species_guess(make_deps, sample_images):
    guess = SpeciesGuess(common_name="Basil", scientific_name="Ocimum basilicum", confidence=0.85)
    deps = make_deps(vision_model=ScriptedStructuredModel([guess]))
    result = make_identify_plant(deps)(_state(sample_images))
    assert result["species"] == guess


def test_failure_yields_an_unknown_zero_confidence_guess(make_deps, sample_images):
    deps = make_deps(vision_model=FailingChatModel(RuntimeError("api down")))
    result = make_identify_plant(deps)(_state(sample_images))
    assert result["species"].confidence == 0.0
    assert result["species"].common_name == "Unknown"
    assert result["errors"]


def test_the_user_supplied_name_is_offered_as_a_hint(make_deps, sample_images):
    model = ScriptedStructuredModel(
        [SpeciesGuess(common_name="Basil", scientific_name=None, confidence=0.9)]
    )
    deps = make_deps(vision_model=model)
    state = _state(sample_images)
    state.plant_name = "my kitchen basil"
    make_identify_plant(deps)(state)
    text_block = model.prompts[0][-1].content[0]["text"]
    assert "my kitchen basil" in text_block


def test_an_already_identified_species_is_not_re_identified(make_deps, sample_images):
    """The re-check flow in Phase 2 reuses this node with the species already known."""
    known = SpeciesGuess(common_name="Basil", scientific_name=None, confidence=0.9)
    model = ScriptedStructuredModel([])
    deps = make_deps(vision_model=model)
    result = make_identify_plant(deps)(_state(sample_images, species=known))
    assert result == {}
    assert model.call_count == 0
