"""The Studio factories call the objects they were wired with the way those objects ask.

`agent/studio.py` is executed by nothing but `langgraph dev`. No test, no request path
and no evaluation run reaches it, so a signature it calls can change underneath it and
the whole suite stays green — the same blind spot `test_port_arity.py` was written for,
one file further out. It happened: tenancy gave every repository a leading `user_id` and
turned plant ids into UUIDs, and this module kept a no-argument `list_all()` and an
`int()` around the id. Studio answered every schema request with a 500.

So the fake here is deliberately not a stub with a convenient signature. `make_deps`
hands over the real `PlantRepository` against the test transaction, which is what makes
these fail when the repository's arguments move again.
"""

import asyncio
from uuid import UUID

import pytest

from agent import studio


@pytest.fixture
def studio_wiring(monkeypatch, make_deps):
    """`chat_graph` with its wiring and its agent builder replaced.

    Only those two: the plant lookup in between is the thing under test. Returns the
    list that records what `make_chat_agent` was asked to scope to.
    """
    deps = make_deps()
    monkeypatch.setattr(studio, "_wiring", lambda: _resolved(deps))

    scoped: list[UUID] = []

    def fake_make_chat_agent(deps, plant_id, checkpointer):
        scoped.append(plant_id)
        return "agent", {}

    monkeypatch.setattr(studio, "make_chat_agent", fake_make_chat_agent)
    return scoped


async def _resolved(value):
    return value


def test_an_empty_config_scopes_chat_to_the_newest_plant(studio_wiring, sample_plant):
    """Opening Studio to look at the graph passes no configuration at all."""
    asyncio.run(studio.chat_graph({}))

    assert studio_wiring == [sample_plant]


def test_a_plant_id_from_the_run_config_arrives_as_a_uuid(studio_wiring, sample_plant):
    """Studio edits that field as JSON, so the id comes back a string, and
    `make_chat_agent` reads a UUID."""
    asyncio.run(studio.chat_graph({"configurable": {"plant_id": str(sample_plant)}}))

    assert studio_wiring == [sample_plant]


def test_no_plants_yet_is_refused_with_an_explanation(studio_wiring):
    """The database is empty until somebody runs a diagnosis; there is no conversation
    to scope until then."""
    with pytest.raises(ValueError, match="No plants exist yet"):
        asyncio.run(studio.chat_graph({}))
