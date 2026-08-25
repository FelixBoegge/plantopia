"""Tests for the plant repository."""

from uuid import UUID

from sqlalchemy import func, select

from core.ids import new_id
from data.models import Observation
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository


def test_create_returns_an_id(db, owner, now):
    repo = PlantRepository(db)
    plant_id = repo.create(
        owner,
        name="Basil",
        species="Ocimum basilicum",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref="img-1",
        now=now(),
    )
    assert isinstance(plant_id, UUID)
    assert plant_id.version == 7


def test_get_round_trips_every_field(db, owner, now):
    repo = PlantRepository(db)
    plant_id = repo.create(
        owner,
        name="Ficus",
        species="Ficus lyrata",
        species_confidence=0.75,
        location_kind="outdoor",
        location_text="Berlin balcony",
        photo_ref="img-2",
        now=now(),
    )
    plant = repo.get(owner, plant_id)
    assert plant is not None
    assert plant.name == "Ficus"
    assert plant.species == "Ficus lyrata"
    assert plant.species_confidence == 0.75
    assert plant.location_kind == "outdoor"
    assert plant.location_text == "Berlin balcony"
    assert plant.photo_ref == "img-2"
    assert plant.created_at == now()


def test_get_returns_none_for_unknown_id(db, owner):
    assert PlantRepository(db).get(owner, new_id()) is None


def test_list_all_returns_plants_newest_first(db, owner, now):
    repo = PlantRepository(db)
    first = repo.create(
        owner,
        name="A",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    second = repo.create(
        owner,
        name="B",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    ids = [
        p.id
        for p in repo.list_all(
            owner,
        )
    ]
    assert ids == [second, first]


def test_duplicate_names_are_allowed_and_distinguishable(db, owner, now):
    repo = PlantRepository(db)
    a = repo.create(
        owner,
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    b = repo.create(
        owner,
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    assert a != b
    assert (
        len(
            repo.list_all(
                owner,
            )
        )
        == 2
    )


def test_update_species_changes_species_and_confidence(db, owner, now):
    repo = PlantRepository(db)
    plant_id = repo.create(
        owner,
        name="Mystery plant",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )

    repo.update_species(owner, plant_id, species="Monstera deliciosa", species_confidence=0.82)

    plant = repo.get(owner, plant_id)
    assert plant is not None
    assert plant.species == "Monstera deliciosa"
    assert plant.species_confidence == 0.82


def test_update_species_leaves_other_fields_untouched(db, owner, now):
    repo = PlantRepository(db)
    plant_id = repo.create(
        owner,
        name="Mystery plant",
        species=None,
        species_confidence=None,
        location_kind="outdoor",
        location_text="Berlin balcony",
        photo_ref="img-3",
        now=now(),
    )

    repo.update_species(owner, plant_id, species="Monstera deliciosa", species_confidence=0.82)

    plant = repo.get(owner, plant_id)
    assert plant is not None
    assert plant.name == "Mystery plant"
    assert plant.location_kind == "outdoor"
    assert plant.location_text == "Berlin balcony"
    assert plant.photo_ref == "img-3"


def test_delete_cascades_to_observations(db, owner, now):
    repo = PlantRepository(db)
    plant_id = repo.create(
        owner,
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    ObservationRepository(db).create(
        owner, plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    db.flush()

    repo.delete(owner, plant_id)
    db.flush()

    remaining = db.scalar(select(func.count()).select_from(Observation))
    assert remaining == 0
