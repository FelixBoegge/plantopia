"""The extraction prompt is the most attractive injection target in the app, so
its structural properties are tested rather than assumed.

The untrusted-input clause itself is covered by the systematic, parametrised rule
in ``test_instruction_hierarchy.py`` (``EXTRACT_PROFILE`` is registered in
``UNTRUSTED_INPUT_PROMPTS`` there) rather than by a bespoke test in this file: that
rule asserts the full behavioural pairing — untrusted text is data *and* must never
be followed as instructions — so a duplicate, narrower check here would only add a
second, weaker place for the same regression to hide.
"""

from agent.prompts.profile import EXTRACT_PROFILE


def test_the_prompt_names_what_must_never_be_stored():
    lowered = EXTRACT_PROFILE.lower()
    for forbidden in ("health", "third part", "password", "one-off"):
        assert forbidden in lowered, f"exclusion not stated: {forbidden}"


def test_the_prompt_requires_verbatim_echoes():
    """Paraphrasing an existing fact into `confirmed` would defeat the UNIQUE
    constraint and accumulate near-duplicates."""
    assert "verbatim" in EXTRACT_PROFILE.lower()
