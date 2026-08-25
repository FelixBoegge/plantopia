"""Unit tests for the learned-profile repository."""

from datetime import UTC, datetime

from data.engine import transaction
from data.repositories.messages import MessageRepository
from data.repositories.plants import PlantRepository
from data.repositories.profile import ProfileRepository

LATER = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)


def _repo(db) -> ProfileRepository:
    return ProfileRepository(db)


def test_a_new_fact_round_trips(db, owner, now):
    repo = _repo(db)
    with transaction(db):
        repo.upsert(owner, fact="lives in Berlin", source="stated", confidence=0.8, now=now())

    facts = repo.list_all(
        owner,
    )
    assert len(facts) == 1
    assert facts[0].fact == "lives in Berlin"
    assert facts[0].source == "stated"
    assert facts[0].confidence == 0.8
    assert facts[0].first_seen == now()
    assert facts[0].last_confirmed == now()


def test_upserting_a_known_fact_confirms_it_rather_than_duplicating(db, owner, now):
    """``user_profile.fact`` is UNIQUE — a second insert of the same text would raise."""
    repo = _repo(db)
    with transaction(db):
        repo.upsert(owner, fact="tends to overwater", source="inferred", confidence=0.5, now=now())
    with transaction(db):
        repo.upsert(owner, fact="tends to overwater", source="inferred", confidence=0.6, now=LATER)

    facts = repo.list_all(
        owner,
    )
    assert len(facts) == 1
    assert facts[0].confidence == 0.6
    assert facts[0].first_seen == now(), "first_seen must not move on confirmation"
    assert facts[0].last_confirmed == LATER


def test_supersede_removes_a_fact(db, owner, now):
    repo = _repo(db)
    with transaction(db):
        repo.upsert(owner, fact="lives in Berlin", source="stated", confidence=0.8, now=now())
    with transaction(db):
        repo.supersede(owner, "lives in Berlin")

    assert (
        repo.list_all(
            owner,
        )
        == []
    )


def test_superseding_an_unknown_fact_is_harmless(db, owner):
    with transaction(db):
        _repo(db).supersede(owner, "never stored")  # must not raise


def test_facts_come_back_highest_confidence_first(db, owner, now):
    repo = _repo(db)
    with transaction(db):
        repo.upsert(owner, fact="low", source="inferred", confidence=0.5, now=now())
        repo.upsert(owner, fact="high", source="stated", confidence=0.9, now=now())

    assert [
        f.fact
        for f in repo.list_all(
            owner,
        )
    ] == ["high", "low"]


def test_the_cursor_is_none_before_anything_is_read(db, owner, sample_plant):
    assert _repo(db).cursor_position(owner, sample_plant) is None


def test_the_cursor_resolves_to_the_message_it_points_at(db, owner, sample_plant, now):
    """The stored cursor is a place in the transcript — a message id. What extraction
    needs is the time that message was written, so it can ask for everything after it."""
    repo = _repo(db)
    messages = MessageRepository(db)
    first = messages.create(
        owner, plant_id=sample_plant, role="user", content="one", tool_calls=None, now=now()
    )
    later = datetime(2026, 3, 5, 9, 0, tzinfo=UTC)
    second = messages.create(
        owner, plant_id=sample_plant, role="user", content="two", tool_calls=None, now=later
    )

    with transaction(db):
        repo.set_cursor(owner, plant_id=sample_plant, last_message_id=first)
    assert repo.cursor_position(owner, sample_plant) == (now(), first)

    with transaction(db):
        repo.set_cursor(owner, plant_id=sample_plant, last_message_id=second)
    assert repo.cursor_position(owner, sample_plant) == (later, second)


def test_another_owners_cursor_is_not_visible(db, owner, other_owner, sample_plant, now):
    repo = _repo(db)
    message_id = MessageRepository(db).create(
        owner, plant_id=sample_plant, role="user", content="one", tool_calls=None, now=now()
    )
    with transaction(db):
        repo.set_cursor(owner, plant_id=sample_plant, last_message_id=message_id)

    assert repo.cursor_position(other_owner, sample_plant) is None


def test_deleting_a_plant_removes_its_cursor(db, owner, sample_plant, now):
    repo = _repo(db)
    message_id = MessageRepository(db).create(
        owner, plant_id=sample_plant, role="user", content="one", tool_calls=None, now=now()
    )
    with transaction(db):
        repo.set_cursor(owner, plant_id=sample_plant, last_message_id=message_id)
    with transaction(db):
        PlantRepository(db).delete(owner, sample_plant)

    assert repo.cursor_position(owner, sample_plant) is None
