"""Tests for the graph state model."""

from agent.state import DiagnosisState, ImageRef


def _image() -> ImageRef:
    return ImageRef(ref="img-1", media_type="image/png", data_b64="aGk=")


def test_state_requires_at_least_one_image():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DiagnosisState(images=[], plant_name="Basil", location_kind="indoor")


def test_state_defaults_are_empty_not_none():
    state = DiagnosisState(images=[_image()], plant_name="Basil", location_kind="indoor")
    assert state.answers == {}
    assert state.questions == []
    assert state.retrieved == []
    assert state.errors == []
    assert state.tools_used == []


def test_optional_results_start_as_none():
    state = DiagnosisState(images=[_image()], plant_name="Basil", location_kind="indoor")
    assert state.species is None
    assert state.symptoms is None
    assert state.differential is None
    assert state.roadmap is None
    assert state.weather is None


def test_rejected_defaults_to_false():
    state = DiagnosisState(images=[_image()], plant_name="Basil", location_kind="indoor")
    assert state.rejected is False
    assert state.rejection_reason is None


def test_species_confidence_is_zero_when_species_unknown():
    state = DiagnosisState(images=[_image()], plant_name="Basil", location_kind="indoor")
    assert state.species_confidence == 0.0


def test_species_confidence_reads_through_to_the_guess():
    from agent.schemas import SpeciesGuess

    state = DiagnosisState(
        images=[_image()],
        plant_name="Basil",
        location_kind="indoor",
        species=SpeciesGuess(common_name="Basil", scientific_name=None, confidence=0.8),
    )
    assert state.species_confidence == 0.8


def test_location_text_is_optional():
    state = DiagnosisState(images=[_image()], plant_name="Basil", location_kind="outdoor")
    assert state.location_text is None
