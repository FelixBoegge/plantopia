"""Watching a chat reply being produced.

The property doing the most work here is that this leaves the same transcript as the
single-request form. It holds by construction — both go through `ChatService.send` — and
it is asserted anyway, because "by construction" is a claim about code that can change.
"""

import json
import time

import pytest
from langgraph.checkpoint.memory import MemorySaver

from api import dependencies, errors
from core.ids import new_id
from data.repositories.messages import MessageRepository
from runs import steps
from services.chat_events import TOOL_NAMES, described
from services.chat_service import ChatService


def _looks_something_up():
    """An agent that consults the corpus once, then answers."""
    from langchain_core.messages import AIMessage

    from tests.fakes.chat_models import ScriptedToolCallingModel

    return ScriptedToolCallingModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_plant_knowledge",
                        "args": {"query": "yellow leaves"},
                        "id": "call-1",
                    }
                ],
            ),
            AIMessage(content="Probably overwatering."),
        ]
    )


NOW_MARKER = "stream"


@pytest.fixture
def chat(client, db, owner, make_deps, now):
    """A chat service with a scripted agent, wired into the application.

    The real dependency builds model clients and a Chroma collection; every test here is
    about what the endpoint does with a reply, not about producing one.
    """

    def _wire(model):
        service = ChatService(
            deps=make_deps(chat_model=model),
            messages=MessageRepository(db),
            checkpointer=MemorySaver(),
            now=now,
        )
        client.app.dependency_overrides[dependencies.chat_service] = lambda: service
        return service

    return _wire


@pytest.fixture
def plain_reply(chat):
    from langchain_core.messages import AIMessage

    from tests.fakes.chat_models import ScriptedToolCallingModel

    return chat(ScriptedToolCallingModel([AIMessage(content="Basil likes damp soil, not wet.")]))


def _read(client, plant_id, content="Why are the leaves yellow?", deadline=15.0):
    received = []
    expires = time.monotonic() + deadline
    with client.stream(
        "POST",
        f"/api/v1/plants/{plant_id}/messages/stream",
        json={"content": content},
        timeout=deadline,
    ) as response:
        assert response.status_code == 200, response.status_code
        event, data = None, None
        for line in response.iter_lines():
            if time.monotonic() > expires:
                break
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
            elif line == "" and event is not None:
                received.append((event, json.loads(data) if data else None))
                event, data = None, None
    return received


def test_a_streamed_message_ends_with_the_reply(client, seeded, plain_reply):
    received = _read(client, seeded["plant_id"])

    kind, payload = received[-1]
    assert kind == steps.COMPLETED
    assert payload["reply"] == "Basil likes damp soil, not wet."


def test_a_streamed_message_is_recorded_in_the_transcript(client, db, seeded, plain_reply):
    _read(client, seeded["plant_id"], content="Why are the leaves yellow?")

    transcript = client.get(f"/api/v1/plants/{seeded['plant_id']}/messages").json()
    assert transcript[-2]["content"] == "Why are the leaves yellow?"
    assert transcript[-1]["content"] == "Basil likes damp soil, not wet."


def test_the_transcript_is_the_same_as_the_single_request_form_leaves(client, db, seeded, chat):
    """Not "similar". The same code writes both, and this is what says so."""
    from langchain_core.messages import AIMessage

    from tests.fakes.chat_models import ScriptedToolCallingModel

    plant_id = seeded["plant_id"]
    chat(ScriptedToolCallingModel([AIMessage(content="One."), AIMessage(content="Two.")]))

    client.post(f"/api/v1/plants/{plant_id}/messages", json={"content": "First question"})
    after_plain = client.get(f"/api/v1/plants/{plant_id}/messages").json()

    _read(client, plant_id, content="Second question")
    after_stream = client.get(f"/api/v1/plants/{plant_id}/messages").json()

    plain_turn = after_plain[-2:]
    stream_turn = after_stream[-2:]
    assert [row["role"] for row in plain_turn] == [row["role"] for row in stream_turn]
    assert set(plain_turn[0]) == set(stream_turn[0])


def test_a_lookup_is_announced_before_the_reply(client, seeded, chat):
    """The point of streaming chat: consulting the corpus and then the web is several
    seconds of silence otherwise, and silence reads as a failure."""
    chat(_looks_something_up())

    received = _read(client, seeded["plant_id"])

    kinds = [kind for kind, _ in received]
    assert steps.TOOL in kinds
    assert kinds.index(steps.TOOL) < kinds.index(steps.COMPLETED)


def test_a_lookup_is_named_in_the_products_language(client, seeded, chat):
    """`search_plant_knowledge_tool` is a function name. A client rendering it is a client
    coupled to one."""
    chat(_looks_something_up())

    received = _read(client, seeded["plant_id"])

    announced = [payload["source"] for kind, payload in received if kind == steps.TOOL]
    assert announced == [described("search_plant_knowledge")]
    assert "search_plant_knowledge" not in str(received)


def test_an_unknown_tool_is_announced_without_naming_itself():
    """The fallback would leak the internal name on exactly the day somebody added a tool
    and forgot the table, which is the only occasion it matters."""
    assert described("some_tool_nobody_listed") == "another source"
    assert "some_tool_nobody_listed" not in described("some_tool_nobody_listed")


def test_every_tool_the_agent_has_is_named(make_deps):
    """The table is total, the same way the graph's step map is."""
    from agent.chat_agent import _make_tools

    named = set(TOOL_NAMES)
    tools, _ = _make_tools(make_deps(), new_id())
    actual = {tool.name for tool in tools}

    assert actual <= named, f"these tools would be announced anonymously: {sorted(actual - named)}"


def test_a_reply_is_recorded_even_if_nobody_is_listening(client, db, seeded, plain_reply):
    """A dropped tunnel costs a view of the answer, not the answer. The work runs to
    completion on its own thread whatever the connection does.
    """
    plant_id = seeded["plant_id"]
    with client.stream(
        "POST",
        f"/api/v1/plants/{plant_id}/messages/stream",
        json={"content": "Why are the leaves yellow?"},
        timeout=15.0,
    ) as response:
        assert response.status_code == 200
        next(response.iter_lines())  # read one line, then walk away

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        transcript = client.get(f"/api/v1/plants/{plant_id}/messages").json()
        if transcript and transcript[-1]["role"] == "assistant":
            break
        time.sleep(0.05)

    assert transcript[-1]["content"] == "Basil likes damp soil, not wet."


def test_streaming_about_another_owners_plant_is_absent(client, db, other_owner, plain_reply):
    from data.repositories.plants import PlantRepository
    from tests.api.conftest import NOW

    theirs = PlantRepository(db).create(
        other_owner,
        name="Their fern",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=NOW,
    )
    db.commit()

    response = client.post(f"/api/v1/plants/{theirs}/messages/stream", json={"content": "hello"})

    assert response.status_code == 404
    assert response.json()["type"] == errors.TYPE_NOT_FOUND


def test_streaming_about_another_owners_plant_records_nothing(client, db, other_owner, plain_reply):
    from data.repositories.plants import PlantRepository
    from tests.api.conftest import NOW

    theirs = PlantRepository(db).create(
        other_owner,
        name="Their fern",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=NOW,
    )
    db.commit()

    client.post(f"/api/v1/plants/{theirs}/messages/stream", json={"content": "hello"})

    assert MessageRepository(db).list_for_plant(other_owner, theirs) == []


def test_the_single_request_endpoint_still_answers(client, seeded, plain_reply):
    """It remains because the evaluation harness and every non-interactive caller want a
    reply rather than fragments to reassemble."""
    response = client.post(
        f"/api/v1/plants/{seeded['plant_id']}/messages", json={"content": "hello"}
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Basil likes damp soil, not wet."
