"""Tests for the chat service — the only surface the chat page calls."""

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from data.db import apply_schema, connect
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.messages import MessageRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.roadmap import RoadmapRepository
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
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )

    turn = service.send(plant_id, "Is this normal?")

    assert "normal" in turn.reply.lower()
    assert turn.escalated is False
    history = service.history(plant_id)
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "Is this normal?"


def test_send_remembers_the_earlier_turns_of_the_same_conversation(make_deps, db, now):
    """Design spec §5 gives the ReAct loop its own checkpointer thread, keyed
    ``chat:{plant_id}``. Without a checkpointer wired into ``create_agent`` that
    thread id is inert: the graph ignores it and every ``send`` arrives as turn one,
    so the model can never refer back to anything the owner said earlier.

    ``ScriptedToolCallingModel.prompts`` records the message list the model actually
    received, which is the only place the difference is observable — the reply text
    is scripted either way.
    """
    plant_id = _plant_id(db, now)
    model = ScriptedToolCallingModel(
        [
            AIMessage(content="Lower-leaf yellowing on a basil is usually a watering issue."),
            AIMessage(content="As I said, let the top few centimetres dry out first."),
        ]
    )
    deps = make_deps(chat_model=model)
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )

    service.send(plant_id, "Why are the lower leaves yellow?")
    service.send(plant_id, "What should I do about it?")

    second_turn = model.prompts[-1]
    assert [m.content for m in second_turn if isinstance(m, HumanMessage)] == [
        "Why are the lower leaves yellow?",
        "What should I do about it?",
    ], "the second turn did not carry the first turn's question — the loop has no memory"
    assert any(isinstance(m, AIMessage) for m in second_turn), (
        "the second turn did not carry the assistant's own earlier reply"
    )


def test_separate_plants_do_not_share_a_chat_thread(make_deps, db, now):
    """The thread id is keyed by plant, so one plant's conversation must not appear
    in another's — the checkpointer is scoped, not global."""
    first = _plant_id(db, now)
    second = PlantRepository(db).create(
        name="Office pothos",
        species="Pothos",
        species_confidence=0.8,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    model = ScriptedToolCallingModel(
        [AIMessage(content="First answer."), AIMessage(content="Second answer.")]
    )
    deps = make_deps(chat_model=model)
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )

    service.send(first, "A question about the basil.")
    service.send(second, "A question about the pothos.")

    second_turn = model.prompts[-1]
    assert [m.content for m in second_turn if isinstance(m, HumanMessage)] == [
        "A question about the pothos."
    ]


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
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )

    turn = service.send(plant_id, "There are new brown spots now, not yellowing.")

    assert turn.escalated is True
    assert "flagged" in turn.reply.lower()


def test_history_is_empty_before_any_messages(make_deps, db, now):
    plant_id = _plant_id(db, now)
    deps = make_deps()
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )
    assert service.history(plant_id) == []


def test_send_commits_durably_not_just_visible_on_the_same_connection(make_deps, now, tmp_path):
    """``send()`` must actually commit: sqlite3 defaults to non-autocommit, and
    without wrapping each write in ``data.db.transaction``, both inserts would sit
    in an open transaction on the connection — invisible to any other connection,
    and lost on process restart. A second, independent connection to the same
    on-disk file is the only way to tell "committed" apart from "merely visible
    to the connection that wrote it"."""
    db_path = tmp_path / "chat.db"
    file_conn = connect(db_path)
    apply_schema(file_conn)
    plant_id = _plant_id(file_conn, now)

    model = ScriptedToolCallingModel([AIMessage(content="Some yellowing is normal for basil.")])
    deps = make_deps(
        chat_model=model,
        plants=PlantRepository(file_conn),
        observations=ObservationRepository(file_conn),
        diagnoses=DiagnosisRepository(file_conn),
        roadmap=RoadmapRepository(file_conn),
    )
    service = ChatService(
        deps=deps, messages=MessageRepository(file_conn), checkpointer=MemorySaver(), now=now
    )

    service.send(plant_id, "Is this normal?")
    assert file_conn.in_transaction is False
    file_conn.close()

    second_conn = connect(db_path)
    history = MessageRepository(second_conn).list_for_plant(plant_id)
    second_conn.close()

    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "Is this normal?"
