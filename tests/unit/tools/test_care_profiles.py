"""Tests for the static care-profile lookup."""

from agent.schemas import CareProfile
from tools.care_profiles import lookup_plant_care_profile


def test_known_species_returns_a_profile():
    profile = lookup_plant_care_profile("Basil")
    assert isinstance(profile, CareProfile)
    assert profile.temperature_c[0] < profile.temperature_c[1]


def test_lookup_is_case_insensitive():
    assert lookup_plant_care_profile("basil") == lookup_plant_care_profile("BASIL")


def test_scientific_name_also_matches():
    assert lookup_plant_care_profile("Ocimum basilicum") == lookup_plant_care_profile("Basil")


def test_unknown_species_returns_none():
    assert lookup_plant_care_profile("Triffid") is None


def test_empty_species_returns_none():
    assert lookup_plant_care_profile("") is None


def test_surrounding_whitespace_is_ignored():
    assert lookup_plant_care_profile("  Basil  ") is not None
