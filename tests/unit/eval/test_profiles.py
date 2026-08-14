"""The evaluation profile fixtures."""

from pathlib import Path

import pytest

from eval.profiles import load_profile

PROFILES = Path("eval/profiles")


def test_the_empty_profile_renders_nothing():
    assert load_profile("empty", PROFILES) == ""


def test_a_seeded_profile_renders_its_facts():
    block = load_profile("overwaterer", PROFILES)
    assert "overwater" in block.lower()


def test_an_unknown_profile_names_itself_in_the_error():
    with pytest.raises(ValueError, match="nosuchprofile"):
        load_profile("nosuchprofile", PROFILES)
