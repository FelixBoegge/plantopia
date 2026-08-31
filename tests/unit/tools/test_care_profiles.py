"""Tests for the static care-profile lookup."""

from agent.schemas import CareOrigin, CareProfile
from tools.care_profiles import lookup_plant_care_profile, make_care_profile_lookup


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


def test_a_hand_written_profile_reports_itself_as_curated():
    """The 18 profiles were written by a person and say so without being edited.

    The default carries them, which is convenient and is the wrong way round for safety: a
    profile that somehow lost its origin would claim to be trustworthy. The researched path
    therefore sets it explicitly rather than relying on this, and its own test asserts that.
    """
    profile = lookup_plant_care_profile("monstera")

    assert profile is not None
    assert profile.origin is CareOrigin.CURATED
    assert profile.sources == []


def test_every_hand_written_profile_is_curated():
    """All of them, not the one that happened to be checked above."""
    from tools.care_profiles import _PROFILES

    assert _PROFILES
    assert all(profile.origin is CareOrigin.CURATED for profile in _PROFILES.values())


class TestTheTiers:
    """Curated, then stored, then researched — and the first one never loses.

    Everything behind the curated tier is a guess a model made from search results. A guess
    that can displace a known answer turns a reliable lookup into an unreliable one for
    exactly the cases that used to work.
    """

    def _researched(self, species: str, water: str = "Researched watering") -> CareProfile:
        return CareProfile(
            species=species,
            light="Researched light",
            water=water,
            temperature_c=(10, 20),
            humidity="Researched humidity",
            origin=CareOrigin.RESEARCHED,
            sources=["web:example.com"],
        )

    def test_curated_beats_stored(self):
        lookup = make_care_profile_lookup(stored=lambda name: self._researched(name))

        found = lookup("monstera")

        assert found is not None
        assert found.origin is CareOrigin.CURATED
        assert found.species == "Monstera deliciosa"

    def test_curated_beats_research(self):
        """And research is never even attempted for a species the curated set covers."""
        attempted = []
        lookup = make_care_profile_lookup(
            research=lambda name: attempted.append(name) or self._researched(name)
        )

        found = lookup("basil")

        assert found is not None
        assert found.origin is CareOrigin.CURATED
        assert attempted == []

    def test_stored_beats_research(self):
        """Paying for research once per species is the whole point of storing one."""
        attempted = []
        lookup = make_care_profile_lookup(
            stored=lambda name: self._researched(name, water="From the cache"),
            research=lambda name: attempted.append(name) or self._researched(name),
        )

        found = lookup("Ocimum africanum")

        assert found is not None
        assert found.water == "From the cache"
        assert attempted == []

    def test_research_runs_when_nothing_else_holds_it(self):
        attempted = []
        lookup = make_care_profile_lookup(
            stored=lambda _name: None,
            research=lambda name: attempted.append(name) or self._researched(name),
        )

        found = lookup("Ocimum africanum")

        assert found is not None
        assert found.origin is CareOrigin.RESEARCHED
        assert attempted == ["Ocimum africanum"]

    def test_a_refusal_is_still_a_miss(self):
        lookup = make_care_profile_lookup(stored=lambda _n: None, research=lambda _n: None)

        assert lookup("Ocimum africanum") is None

    def test_with_no_tiers_it_is_exactly_todays_behaviour(self):
        """What the evaluation harness gets, and what the stored tier landed behind before
        anything researched anything."""
        lookup = make_care_profile_lookup()

        assert lookup("monstera") is not None
        assert lookup("Ocimum africanum") is None

    def test_an_empty_species_reaches_no_tier(self):
        """A blank name is not a species nothing knows about; it is not a question."""
        attempted = []
        lookup = make_care_profile_lookup(
            stored=lambda name: attempted.append(name) or None,
            research=lambda name: attempted.append(name) or None,
        )

        assert lookup("   ") is None
        assert attempted == []
