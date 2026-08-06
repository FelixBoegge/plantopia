"""Tests for the plant repository."""

from data.repositories.plants import PlantRepository


def test_create_returns_an_id(db, now):
    repo = PlantRepository(db)
    plant_id = repo.create(
        name="Basil",
        species="Ocimum basilicum",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref="img-1",
        now=now(),
    )
    assert isinstance(plant_id, int)
    assert plant_id > 0


def test_get_round_trips_every_field(db, now):
    repo = PlantRepository(db)
    plant_id = repo.create(
        name="Ficus",
        species="Ficus lyrata",
        species_confidence=0.75,
        location_kind="outdoor",
        location_text="Berlin balcony",
        photo_ref="img-2",
        now=now(),
    )
    plant = repo.get(plant_id)
    assert plant is not None
    assert plant.name == "Ficus"
    assert plant.species == "Ficus lyrata"
    assert plant.species_confidence == 0.75
    assert plant.location_kind == "outdoor"
    assert plant.location_text == "Berlin balcony"
    assert plant.photo_ref == "img-2"
    assert plant.created_at == now()


def test_get_returns_none_for_unknown_id(db):
    assert PlantRepository(db).get(404) is None


def test_list_all_returns_plants_newest_first(db, now):
    repo = PlantRepository(db)
    first = repo.create(
        name="A",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    second = repo.create(
        name="B",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    ids = [p.id for p in repo.list_all()]
    assert ids == [second, first]


def test_duplicate_names_are_allowed_and_distinguishable(db, now):
    repo = PlantRepository(db)
    a = repo.create(
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    b = repo.create(
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    assert a != b
    assert len(repo.list_all()) == 2


def test_delete_cascades_to_observations(db, now):
    repo = PlantRepository(db)
    plant_id = repo.create(
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    db.execute(
        "INSERT INTO observations (plant_id, kind, photo_refs, created_at) VALUES (?, ?, ?, ?)",
        (plant_id, "initial", "[]", now().isoformat()),
    )
    db.commit()

    repo.delete(plant_id)

    remaining = db.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"]
    assert remaining == 0
