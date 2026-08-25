"""Conversation about one plant.

The agent is scripted. This tier asserts the HTTP contract — what comes back, what is
recorded — and never that a model said something sensible.
"""

from datetime import UTC, datetime

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from api import dependencies
from core.ids import new_id
from data.repositories.messages import MessageRepository
from services.chat_service import ChatService
from tests.fakes.chat_models import ScriptedToolCallingModel

REPLY = "Some yellowing on the oldest leaves is normal for basil."
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def chatting(client, db, owner, make_deps):
    """The chat service with a scripted agent, on the test session."""

    def _service() -> ChatService:
        deps = make_deps(chat_model=ScriptedToolCallingModel([AIMessage(content=REPLY)]))
        return ChatService(
            deps=deps,
            messages=MessageRepository(db),
            checkpointer=MemorySaver(),
            now=lambda: NOW,
        )

    client.app.dependency_overrides[dependencies.chat_service] = _service
    return client


def test_the_transcript_comes_back_oldest_first(chatting, seeded):
    response = chatting.get(f"/api/v1/plants/{seeded['plant_id']}/messages")

    assert response.status_code == 200
    body = response.json()
    assert [m["content"] for m in body] == ["Is this normal?"]
    assert body[0]["role"] == "user"


def test_a_plant_with_no_conversation_returns_an_empty_list(chatting, seeded, db, owner):
    from data.repositories.plants import PlantRepository

    other = PlantRepository(db).create(
        owner,
        name="Pothos",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=NOW,
    )
    db.flush()

    assert chatting.get(f"/api/v1/plants/{other}/messages").json() == []


def test_sending_a_message_returns_the_reply(chatting, seeded):
    response = chatting.post(
        f"/api/v1/plants/{seeded['plant_id']}/messages", json={"content": "Is this normal?"}
    )

    assert response.status_code == 200
    assert response.json()["reply"] == REPLY
    assert response.json()["escalated"] is False


def test_both_the_message_and_the_reply_are_recorded(chatting, seeded):
    chatting.post(f"/api/v1/plants/{seeded['plant_id']}/messages", json={"content": "What now?"})

    transcript = chatting.get(f"/api/v1/plants/{seeded['plant_id']}/messages").json()
    assert [m["role"] for m in transcript] == ["user", "user", "assistant"]
    assert transcript[-1]["content"] == REPLY


def test_messaging_an_unknown_plant_is_not_found(chatting):
    response = chatting.post(f"/api/v1/plants/{new_id()}/messages", json={"content": "hi"})

    assert response.status_code == 404


def test_reading_an_unknown_plants_transcript_is_not_found(chatting):
    assert chatting.get(f"/api/v1/plants/{new_id()}/messages").status_code == 404


def test_an_empty_message_is_refused(chatting, seeded):
    response = chatting.post(f"/api/v1/plants/{seeded['plant_id']}/messages", json={"content": ""})

    assert response.status_code == 422
