"""Tests for the chat service — the only surface the chat page calls."""

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.schemas import Passage
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


def test_the_tool_calls_of_a_turn_are_persisted_with_the_reply(make_deps, db, now):
    """``MessageRecord.tool_calls``, its JSON round-trip, and the ``"tool"`` role were
    all built in an earlier task and then never written to — ``send`` hardcoded
    ``tool_calls=None``. Design spec §5 wants the transcript rendered "with tool calls
    shown collapsibly", which needs them recorded in the first place."""
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

    service.send(plant_id, "There are new brown spots now, not yellowing.")

    assistant = service.history(plant_id)[-1]
    assert assistant.role == "assistant"
    assert assistant.tool_calls is not None
    assert [call["name"] for call in assistant.tool_calls] == ["suggest_new_diagnosis"]
    assert assistant.tool_calls[0]["args"] == {"reason": "new brown spots"}
    # The tool's own output is recorded alongside the call, matched by tool_call_id.
    assert "flagged" in assistant.tool_calls[0]["result"].lower()


def test_a_turn_with_no_tool_calls_persists_none(make_deps, db, now):
    """``None``, not an empty list: ``MessageRepository`` round-trips a falsy value to
    ``None`` anyway, and the UI keys the collapsible section off "is there anything"."""
    plant_id = _plant_id(db, now)
    model = ScriptedToolCallingModel([AIMessage(content="Some yellowing is normal.")])
    deps = make_deps(chat_model=model)
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )

    service.send(plant_id, "Is this normal?")

    assert service.history(plant_id)[-1].tool_calls is None


def test_only_this_turns_tool_calls_are_persisted(make_deps, db, now):
    """Now that the loop has memory, ``result["messages"]`` holds the whole
    conversation — so a naive sweep of it would re-record every earlier turn's tool
    calls onto every later reply."""
    plant_id = _plant_id(db, now)
    model = ScriptedToolCallingModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "get_plant_journal", "args": {}, "id": "call1"}],
            ),
            AIMessage(content="Nothing on record yet."),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "lookup_plant_care_profile", "args": {"species": "Basil"}, "id": "c2"}
                ],
            ),
            AIMessage(content="Basil wants full sun."),
        ]
    )
    deps = make_deps(chat_model=model)
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )

    service.send(plant_id, "What has happened to this plant so far?")
    service.send(plant_id, "And what does a basil want generally?")

    replies = [m for m in service.history(plant_id) if m.role == "assistant"]
    assert [call["name"] for call in replies[0].tool_calls] == ["get_plant_journal"]
    assert [call["name"] for call in replies[1].tool_calls] == ["lookup_plant_care_profile"]


def test_a_long_tool_result_is_truncated(make_deps, db, now):
    """Four retrieved corpus passages or a whole journal can run to thousands of
    characters. The stored summary shows what the agent consulted; it is not meant to
    be a second copy of it."""
    from services.chat_service import _MAX_RESULT_CHARS

    plant_id = _plant_id(db, now)
    long_text = "x" * (_MAX_RESULT_CHARS * 3)
    model = ScriptedToolCallingModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "web_search_plant_info", "args": {"query": "q"}, "id": "c1"}],
            ),
            AIMessage(content="Here is what I found."),
        ]
    )
    deps = make_deps(
        chat_model=model,
        web_search=lambda query: [
            Passage(doc_id="web:1", section="body", text=long_text, score=0.5)
        ],
    )
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )

    service.send(plant_id, "Anything new on this online?")

    stored = service.history(plant_id)[-1].tool_calls[0]["result"]
    assert len(stored) == _MAX_RESULT_CHARS + 1  # the ellipsis
    assert stored.endswith("…")


def test_extracting_from_a_message_list_with_no_user_turn_is_not_a_crash():
    """Defensive: ``send`` always puts a HumanMessage in, but the boundary scan should
    fall back to "the whole list" rather than silently returning nothing if some future
    caller does not."""
    from services.chat_service import _extract_tool_calls

    messages = [
        AIMessage(content="", tool_calls=[{"name": "get_plant_journal", "args": {}, "id": "c1"}]),
        AIMessage(content="Nothing yet."),
    ]
    assert [c["name"] for c in _extract_tool_calls(messages)] == ["get_plant_journal"]


def test_a_block_list_reply_is_coerced_to_text(make_deps, db, now):
    """Some providers return content as a list of blocks rather than a string. sqlite3
    rejects a list outright (InterfaceError), so the reply is coerced before it reaches
    the insert."""
    plant_id = _plant_id(db, now)
    model = ScriptedToolCallingModel(
        [AIMessage(content=[{"type": "text", "text": "Yellowing is normal."}])]
    )
    deps = make_deps(chat_model=model)
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )

    turn = service.send(plant_id, "Is this normal?")

    assert isinstance(turn.reply, str)
    assert "Yellowing is normal." in turn.reply
    assert service.history(plant_id)[-1].content == turn.reply


def test_an_empty_reply_gets_stand_in_text_not_a_blank_row(make_deps, db, now):
    """``messages.content`` is NOT NULL, and a blank bubble tells the owner nothing."""
    plant_id = _plant_id(db, now)
    model = ScriptedToolCallingModel([AIMessage(content="")])
    deps = make_deps(chat_model=model)
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )

    turn = service.send(plant_id, "Is this normal?")

    assert turn.reply
    assert service.history(plant_id)[-1].content == turn.reply


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


def test_a_completed_chat_turn_triggers_profile_learning(make_deps, db, now):
    """Called after the assistant's reply is committed, so its failure cannot cost one."""
    calls = []

    class _Spy:
        def learn_from_chat(self, plant_id, messages):
            calls.append(plant_id)

    plant_id = _plant_id(db, now)
    model = ScriptedToolCallingModel([AIMessage(content="Some yellowing is normal for basil.")])
    deps = make_deps(chat_model=model)
    service = ChatService(
        deps=deps,
        messages=MessageRepository(db),
        checkpointer=MemorySaver(),
        now=now,
        profile=_Spy(),
    )

    service.send(plant_id, "Is this normal?")

    assert calls == [plant_id]


def test_a_failing_profile_service_does_not_break_the_chat_reply(make_deps, db, now):
    class _Boom:
        def learn_from_chat(self, plant_id, messages):
            raise RuntimeError("boom")

    plant_id = _plant_id(db, now)
    model = ScriptedToolCallingModel([AIMessage(content="Some yellowing is normal for basil.")])
    deps = make_deps(chat_model=model)
    service = ChatService(
        deps=deps,
        messages=MessageRepository(db),
        checkpointer=MemorySaver(),
        now=now,
        profile=_Boom(),
    )

    turn = service.send(plant_id, "Is this normal?")

    assert turn.reply
    assert service.history(plant_id)[-1].role == "assistant"
