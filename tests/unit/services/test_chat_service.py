"""Tests for the chat service — the only surface the chat page calls."""

from langchain_core.messages import AIMessage

from data.repositories.messages import MessageRepository
from data.repositories.plants import PlantRepository
from services.chat_service import ChatService
from tests.fakes.chat_models import ScriptedToolCallingModel


def _plant_id(db, now) -> int:
    return PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )


def test_send_persists_both_sides_of_the_exchange(make_deps, db, now):
    plant_id = _plant_id(db, now)
    model = ScriptedToolCallingModel(
        [AIMessage(content="Some yellowing on lower leaves is normal for basil.")]
    )
    deps = make_deps(chat_model=model)
    service = ChatService(deps=deps, messages=MessageRepository(db), now=now)

    turn = service.send(plant_id, "Is this normal?")

    assert "normal" in turn.reply.lower()
    assert turn.escalated is False
    history = service.history(plant_id)
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "Is this normal?"


def test_send_reports_an_escalation(make_deps, db, now):
    plant_id = _plant_id(db, now)
    model = ScriptedToolCallingModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "suggest_new_diagnosis",
                        "args": {"reason": "new brown spots"},
                        "id": "call1",
                    }
                ],
            ),
            AIMessage(content="I've flagged this for a fresh look."),
        ]
    )
    deps = make_deps(chat_model=model)
    service = ChatService(deps=deps, messages=MessageRepository(db), now=now)

    turn = service.send(plant_id, "There are new brown spots now, not yellowing.")

    assert turn.escalated is True
    assert "flagged" in turn.reply.lower()


def test_history_is_empty_before_any_messages(make_deps, db, now):
    plant_id = _plant_id(db, now)
    deps = make_deps()
    service = ChatService(deps=deps, messages=MessageRepository(db), now=now)
    assert service.history(plant_id) == []
