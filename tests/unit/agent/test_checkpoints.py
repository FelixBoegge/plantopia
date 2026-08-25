"""Checkpoints in Postgres: survival, isolation, removal.

Against the real checkpointer and the real database, because what is being tested is
precisely that state outlives the process holding it. A fake would assert that a fake
remembers things.

No model calls: the graph under test is a two-node toy that interrupts.
"""

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from agent.checkpoints import build_checkpointer, checkpointer_url, delete_for_user
from agent.threads import diagnosis_thread
from core.config import Settings
from core.ids import new_id


class _State(TypedDict, total=False):
    started: str
    answer: str


def _paused_graph(checkpointer):
    """A graph that records something, pauses for an answer, then records that."""

    def begin(state: _State) -> dict:
        return {"started": "yes"}

    def ask(state: _State) -> dict:
        return {"answer": interrupt("what colour?")}

    graph = StateGraph(_State)
    graph.add_node("begin", begin)
    graph.add_node("ask", ask)
    graph.add_edge(START, "begin")
    graph.add_edge("begin", "ask")
    graph.add_edge("ask", END)
    return graph.compile(checkpointer=checkpointer)


@pytest.fixture
def url():
    return checkpointer_url(Settings(_env_file=None, openrouter_api_key="sk-test"))


@pytest.fixture
def saver(url):
    return build_checkpointer(url)


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def test_a_paused_run_resumes_with_its_work_intact(saver, url):
    """The property M15's SQLite files provided and a container filesystem does not: a
    run paused for the owner's answers survives whatever happens to the process."""
    owner = new_id()
    thread = diagnosis_thread(owner)
    _paused_graph(saver).invoke({}, _config(thread))

    # A second checkpointer object over the same database — as a restarted process gets.
    rebuilt = build_checkpointer(url)
    result = _paused_graph(rebuilt).invoke(Command(resume="green"), _config(thread))

    assert result["started"] == "yes", "work done before the pause was lost"
    assert result["answer"] == "green"

    delete_for_user(url, owner)


def test_a_run_is_paused_until_it_is_answered(saver, url):
    owner = new_id()
    thread = diagnosis_thread(owner)
    graph = _paused_graph(saver)
    graph.invoke({}, _config(thread))

    state = graph.get_state(_config(thread))

    assert state.next, "the graph should still be waiting"
    assert "answer" not in state.values

    delete_for_user(url, owner)


def test_two_owners_runs_do_not_meet(saver, url):
    """Handles carry the owner, so two runs cannot collide however similar the work."""
    first, second = new_id(), new_id()
    # Held, not rebuilt: a diagnosis handle is random by design, so calling the helper
    # twice gives two different runs — which is the point, but not what this asserts.
    mine, theirs = diagnosis_thread(first), diagnosis_thread(second)
    graph = _paused_graph(saver)
    graph.invoke({}, _config(mine))
    graph.invoke({}, _config(theirs))

    resumed = graph.invoke(Command(resume="mine"), _config(mine))
    assert resumed["answer"] == "mine"
    assert graph.get_state(_config(theirs)).next, "the other run should still be paused"

    delete_for_user(url, first)
    delete_for_user(url, second)


def test_removing_an_owners_state_leaves_other_owners_alone(saver, url):
    """Checkpoint tables belong to LangGraph, so no cascade reaches them — deletion is a
    query over the thread-id prefix, and it has to be exact about whose rows it takes."""
    mine, theirs = new_id(), new_id()
    my_thread, their_thread = diagnosis_thread(mine), diagnosis_thread(theirs)
    graph = _paused_graph(saver)
    graph.invoke({}, _config(my_thread))
    graph.invoke({}, _config(their_thread))

    removed = delete_for_user(url, mine)

    assert removed > 0
    assert not graph.get_state(_config(my_thread)).next, "my run should be gone"
    assert graph.get_state(_config(their_thread)).next, "their run should be untouched"

    delete_for_user(url, theirs)


def test_removing_state_for_an_owner_with_none_is_harmless(url):
    assert delete_for_user(url, new_id()) == 0


def test_the_checkpointer_url_drops_the_sqlalchemy_driver():
    """psycopg does not understand postgresql+psycopg://, and says so unhelpfully."""
    settings = Settings(
        _env_file=None,
        openrouter_api_key="sk-test",
        database_url="postgresql+psycopg://u:p@host:5433/db",
    )

    assert checkpointer_url(settings) == "postgresql://u:p@host:5433/db"
