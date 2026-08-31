"""Tests for the researched care-profile cache.

The one repository here that takes no ``user_id``. What a species wants is the same fact for
everybody, so the table holds reference data rather than records — the argument
`corpus_chunks` already makes.
"""

from datetime import UTC, datetime

import pytest

from agent.schemas import CareOrigin, CareProfile
from data.repositories.care_profiles import CareProfileRepository, normalise

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def _researched(species: str = "Ocimum africanum", **overrides) -> CareProfile:
    fields = {
        "species": species,
        "light": "Six or more hours of direct sun",
        "water": "Keep evenly moist; do not let it dry out",
        "temperature_c": (18, 30),
        "humidity": "Average indoor humidity is fine",
        "origin": CareOrigin.RESEARCHED,
        "sources": ["web:example.com/thai-basil", "web:rhs.org.uk/ocimum"],
        **overrides,
    }
    return CareProfile(**fields)


class TestRoundTrip:
    def test_a_profile_survives_the_trip(self, db):
        repo = CareProfileRepository(db)
        repo.put(_researched(), now=NOW)

        read = repo.get("Ocimum africanum")

        assert read is not None
        assert read.species == "Ocimum africanum"
        assert read.light == "Six or more hours of direct sun"
        assert read.temperature_c == (18, 30)

    def test_the_sources_survive(self, db):
        """A profile a model assembled from four search results is a guess, and a guess whose
        provenance is gone cannot be checked afterwards by anybody."""
        repo = CareProfileRepository(db)
        repo.put(_researched(), now=NOW)

        read = repo.get("Ocimum africanum")

        assert read is not None
        assert read.sources == ["web:example.com/thai-basil", "web:rhs.org.uk/ocimum"]

    def test_a_stored_profile_reads_back_as_researched(self, db):
        """Set explicitly rather than defaulted.

        `CareProfile.origin` defaults to curated so the hand-written table needs no edit,
        which is convenient and is the wrong way round for safety: a stored guess that fell
        back on the default would read back as a curated fact.
        """
        repo = CareProfileRepository(db)
        repo.put(_researched(), now=NOW)

        read = repo.get("Ocimum africanum")

        assert read is not None
        assert read.origin is CareOrigin.RESEARCHED

    def test_an_unknown_species_is_none(self, db):
        assert CareProfileRepository(db).get("Nothing At All") is None

    def test_an_empty_species_is_none(self, db):
        assert CareProfileRepository(db).get("   ") is None


class TestTheKey:
    def test_three_spellings_are_one_row(self, db):
        """Otherwise a species researched once is researched again under a different casing,
        and the cache stops being a cache."""
        repo = CareProfileRepository(db)
        repo.put(_researched(species="Ocimum africanum"), now=NOW)

        assert repo.get("ocimum africanum") is not None
        assert repo.get("OCIMUM AFRICANUM") is not None
        assert repo.get("  Ocimum Africanum  ") is not None

    def test_it_matches_what_the_curated_tier_does(self):
        """If the two normalisations ever disagreed, a species could be curated under one
        spelling and researched under another, and the trusted tier would stop winning."""
        for name in ("Monstera Deliciosa", "  basil ", "OCIMUM"):
            assert normalise(name) == name.strip().lower()

    def test_the_display_name_is_not_the_key(self, db):
        """The key is lowercased for matching; nobody wants to read "ocimum africanum" in a
        care note."""
        repo = CareProfileRepository(db)
        repo.put(_researched(species="Ocimum Africanum"), now=NOW)

        read = repo.get("ocimum africanum")

        assert read is not None
        assert read.species == "Ocimum Africanum"


class TestWhatItRefusesToHold:
    def test_a_curated_profile_cannot_be_stored(self, db):
        """The curated tier is a Python dict that always wins, so a row here labelled curated
        could never be reached — it would be a lie in the database that no read could
        expose."""
        curated = CareProfile(
            species="Basil",
            light="Sun",
            water="Moist",
            temperature_c=(18, 30),
            humidity="Average",
        )

        with pytest.raises(ValueError, match="only researched profiles"):
            CareProfileRepository(db).put(curated, now=NOW)

    def test_nothing_was_written(self, db):
        curated = CareProfile(
            species="Basil", light="Sun", water="Moist", temperature_c=(18, 30), humidity="Average"
        )
        repo = CareProfileRepository(db)

        with pytest.raises(ValueError):
            repo.put(curated, now=NOW)

        assert repo.get("Basil") is None


class TestWritingTwice:
    def test_the_second_write_wins_rather_than_failing(self, db):
        """Two runs can research the same species concurrently: both find nothing, both
        research, both write. The second is the same fact as the first, so failing the later
        diagnosis over a race that produced the right answer twice would be absurd."""
        repo = CareProfileRepository(db)
        repo.put(_researched(), now=NOW)
        repo.put(_researched(water="Water deeply once the top of the pot dries"), now=NOW)

        read = repo.get("Ocimum africanum")

        assert read is not None
        assert read.water == "Water deeply once the top of the pot dries"

    def test_a_different_casing_does_not_make_a_second_row(self, db):
        repo = CareProfileRepository(db)
        repo.put(_researched(species="Ocimum africanum"), now=NOW)
        repo.put(_researched(species="OCIMUM AFRICANUM", humidity="Dry air is fine"), now=NOW)

        read = repo.get("ocimum africanum")

        assert read is not None
        assert read.humidity == "Dry air is fine"
