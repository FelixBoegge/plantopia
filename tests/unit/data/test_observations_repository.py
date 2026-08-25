"""Tests for the observation repository."""

from uuid import UUID

import pytest

from core.ids import new_id
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
