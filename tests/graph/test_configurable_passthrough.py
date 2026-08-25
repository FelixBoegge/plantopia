"""Spike: can a live object ride through `configurable` into a node?

The Phase 3 cost design passes a `UsageCollector` this way so `persist` can read it
(spec §2.1). A callback object is not JSON-serialisable, and a checkpointer writes
checkpoint metadata derived from config — so this has to be proven against the real
saver, not assumed. Now proven against the Postgres one, since that is the saver the
application actually runs.
"""

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from agent.checkpoints import build_checkpointer, checkpointer_url, delete_for_user
from agent.threads import diagnosis_thread
from core.config import Settings
from core.ids import new_id


class _State(BaseModel):
    seen: str = ""


class _NotSerialisable:
    """Stands in for UsageCollector: json.dumps() raises on this."""

    def label(self) -> str:
        return "alive"


def test_configurable_carries_a_live_object_through_checkpointing():
    def node(state: _State, config) -> dict:
        obj = config["configurable"]["probe"]
        return {"seen": obj.label()}

    builder = StateGraph(_State)
    builder.add_node("node", node)
    builder.add_edge(START, "node")
    builder.add_edge("node", END)

    url = checkpointer_url(Settings(_env_file=None, openrouter_api_key="sk-test"))
    graph = builder.compile(checkpointer=build_checkpointer(url))
    owner = new_id()

    try:
        result = graph.invoke(
            _State(),
            {"configurable": {"thread_id": diagnosis_thread(owner), "probe": _NotSerialisable()}},
        )

        assert result["seen"] == "alive"
    finally:
        delete_for_user(url, owner)
