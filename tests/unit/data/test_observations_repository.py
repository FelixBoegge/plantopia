"""Tests for the observation repository."""

from uuid import UUID

import pytest

from core.ids import new_id
from data.models import Observation
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository


@pytest.fixture
def plant_id(db, owner, now) -> UUID:
    return PlantRepository(db).create(
        owner,
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )


def test_photo_refs_round_trip_as_a_list(db, owner, now, plant_id):
    repo = ObservationRepository(db)
    obs_id = repo.create(
        owner,
        plant_id=plant_id,
        kind="initial",
        photo_refs=["img-1", "img-2", "img-3"],
        user_notes="leaves drooping",
        now=now(),
    )
    observation = repo.get(owner, obs_id)
    assert observation is not None
    assert observation.photo_refs == ["img-1", "img-2", "img-3"]
    assert observation.user_notes == "leaves drooping"
    assert observation.kind == "initial"


def test_empty_photo_refs_round_trip(db, owner, now, plant_id):
    repo = ObservationRepository(db)
    obs_id = repo.create(
        owner, plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    assert repo.get(owner, obs_id).photo_refs == []


def test_list_for_plant_is_chronological(db, owner, now, plant_id):
    repo = ObservationRepository(db)
    first = repo.create(
        owner, plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    second = repo.create(
        owner, plant_id=plant_id, kind="recheck", photo_refs=[], user_notes=None, now=now()
    )
    assert [o.id for o in repo.list_for_plant(owner, plant_id)] == [first, second]


def test_get_returns_none_for_unknown_id(db, owner):
    assert ObservationRepository(db).get(owner, new_id()) is None


class TestWhatThePhotographsSaid:
    """Recorded on the observation, separately from when it was uploaded.

    Null in all three means no photograph declared anything, which is most of them and is
    not a failure — and is what every row written before these columns existed says about
    itself, truthfully, with nothing to backfill from.
    """

    def test_a_capture_date_and_a_coarse_position_round_trip(self, db, owner, now):
        from datetime import UTC, datetime

        from data.repositories.plants import PlantRepository

        plant_id = PlantRepository(db).create(
            owner,
            name="Test plant",
            species=None,
            species_confidence=None,
            location_kind="outdoor",
            location_text=None,
            photo_ref=None,
            now=now(),
        )
        taken = datetime(2026, 8, 10, 10, 50, 49, tzinfo=UTC)

        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=plant_id,
            kind="initial",
            photo_refs=["img-1"],
            user_notes=None,
            now=now(),
            captured_at=taken,
            latitude=54.5,
            longitude=3.2,
        )

        row = db.get(Observation, observation_id)
        assert row.captured_at == taken
        assert (row.latitude, row.longitude) == (54.5, 3.2)
        assert row.created_at != taken, (
            "the upload moment and the capture moment are different facts"
        )

    def test_an_observation_that_knew_neither(self, db, owner, now):
        from data.repositories.plants import PlantRepository

        plant_id = PlantRepository(db).create(
            owner,
            name="Test plant",
            species=None,
            species_confidence=None,
            location_kind="indoor",
            location_text=None,
            photo_ref=None,
            now=now(),
        )

        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=plant_id,
            kind="initial",
            photo_refs=["img-1"],
            user_notes=None,
            now=now(),
        )

        row = db.get(Observation, observation_id)
        assert row.captured_at is None
        assert row.latitude is None
        assert row.longitude is None
