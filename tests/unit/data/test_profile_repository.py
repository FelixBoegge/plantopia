"""Unit tests for the learned-profile repository."""

from datetime import UTC, datetime

from data.db import transaction
from data.repositories.profile import ProfileRepository

LATER = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)


def _repo(db) -> ProfileRepository:
    return ProfileRepository(db)


def test_a_new_fact_round_trips(db, now):
    repo = _repo(db)
    with transaction(db):
        repo.upsert(fact="lives in Berlin", source="stated", confidence=0.8, now=now())

    facts = repo.list_all()
    assert len(facts) == 1
    assert facts[0].fact == "lives in Berlin"
    assert facts[0].source == "stated"
    assert facts[0].confidence == 0.8
    assert facts[0].first_seen == now()
    assert facts[0].last_confirmed == now()


def test_upserting_a_known_fact_confirms_it_rather_than_duplicating(db, now):
    """``user_profile.fact`` is UNIQUE — a second insert of the same text would raise."""
    repo = _repo(db)
    with transaction(db):
        repo.upsert(fact="tends to overwater", source="inferred", confidence=0.5, now=now())
    with transaction(db):
        repo.upsert(fact="tends to overwater", source="inferred", confidence=0.6, now=LATER)

    facts = repo.list_all()
    assert len(facts) == 1
    assert facts[0].confidence == 0.6
    assert facts[0].first_seen == now(), "first_seen must not move on confirmation"
    assert facts[0].last_confirmed == LATER


def test_supersede_removes_a_fact(db, now):
    repo = _repo(db)
    with transaction(db):
        repo.upsert(fact="lives in Berlin", source="stated", confidence=0.8, now=now())
    with transaction(db):
        repo.supersede("lives in Berlin")

    assert repo.list_all() == []


def test_superseding_an_unknown_fact_is_harmless(db):
    with transaction(db):
        _repo(db).supersede("never stored")  # must not raise


def test_facts_come_back_highest_confidence_first(db, now):
    repo = _repo(db)
    with transaction(db):
        repo.upsert(fact="low", source="inferred", confidence=0.5, now=now())
        repo.upsert(fact="high", source="stated", confidence=0.9, now=now())

    assert [f.fact for f in repo.list_all()] == ["high", "low"]


def test_cursor_is_none_before_anything_is_read(db):
    assert _repo(db).cursor_for(1) is None


def test_cursor_round_trips_and_advances(db, sample_plant):
    repo = _repo(db)
    with transaction(db):
        repo.set_cursor(plant_id=sample_plant, last_message_id=7)
    assert repo.cursor_for(sample_plant) == 7

    with transaction(db):
        repo.set_cursor(plant_id=sample_plant, last_message_id=12)
    assert repo.cursor_for(sample_plant) == 12


def test_deleting_a_plant_removes_its_cursor(db, sample_plant):
    repo = _repo(db)
    with transaction(db):
        repo.set_cursor(plant_id=sample_plant, last_message_id=7)
    with transaction(db):
        db.execute("DELETE FROM plants WHERE id = ?", (sample_plant,))

    assert repo.cursor_for(sample_plant) is None
