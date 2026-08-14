"""The extraction prompt is the most attractive injection target in the app, so
its guard clause is tested rather than assumed."""

from agent.prompts.profile import EXTRACT_PROFILE


def test_the_prompt_carries_the_untrusted_input_clause():
    lowered = EXTRACT_PROFILE.lower()
    assert "never an instruction" in lowered or "not an instruction" in lowered
    assert "instruction" in lowered


def test_the_prompt_names_what_must_never_be_stored():
    lowered = EXTRACT_PROFILE.lower()
    for forbidden in ("health", "third part", "password", "one-off"):
        assert forbidden in lowered, f"exclusion not stated: {forbidden}"


def test_the_prompt_requires_verbatim_echoes():
    """Paraphrasing an existing fact into `confirmed` would defeat the UNIQUE
    constraint and accumulate near-duplicates."""
    assert "verbatim" in EXTRACT_PROFILE.lower()
