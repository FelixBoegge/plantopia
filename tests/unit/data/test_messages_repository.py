"""Tests for chat transcript persistence."""

from data.repositories.messages import MessageRepository
from data.repositories.plants import PlantRepository


def _plant_id(db, now) -> int:
    return PlantRepository(db).create(
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )


def test_create_and_list_roundtrip(db, now):
    plant_id = _plant_id(db, now)
    repo = MessageRepository(db)
    repo.create(
        plant_id=plant_id,
        role="user",
        content="Is this normal for a basil?",
        tool_calls=None,
        now=now(),
    )
    repo.create(
        plant_id=plant_id,
        role="assistant",
        content="Some yellowing on lower leaves is normal.",
        tool_calls=[
            {
                "name": "lookup_plant_care_profile",
                "content": "Basil: full sun, evenly moist.",
            }
        ],
        now=now(),
    )

    messages = repo.list_for_plant(plant_id)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].tool_calls[0]["name"] == "lookup_plant_care_profile"


def test_messages_without_tool_calls_deserialise_to_none(db, now):
    plant_id = _plant_id(db, now)
    repo = MessageRepository(db)
    repo.create(plant_id=plant_id, role="user", content="hello", tool_calls=None, now=now())
    assert repo.list_for_plant(plant_id)[0].tool_calls is None


def test_list_for_plant_is_ordered_oldest_first(db, now):
    plant_id = _plant_id(db, now)
    repo = MessageRepository(db)
    repo.create(plant_id=plant_id, role="user", content="first", tool_calls=None, now=now())
    repo.create(plant_id=plant_id, role="assistant", content="second", tool_calls=None, now=now())
    assert [m.content for m in repo.list_for_plant(plant_id)] == ["first", "second"]


def test_empty_tool_calls_list_roundtrips_faithfully(db, now):
    plant_id = _plant_id(db, now)
    repo = MessageRepository(db)
    repo.create(plant_id=plant_id, role="assistant", content="hello", tool_calls=[], now=now())
    assert repo.list_for_plant(plant_id)[0].tool_calls == []
