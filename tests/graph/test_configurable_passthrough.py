"""Spike: can a live object ride through `configurable` into a node?

The Phase 3 cost design passes a `UsageCollector` this way so `persist` can read
it (spec §2.1). A callback object is not JSON-serialisable, and the SQLite
checkpointer writes checkpoint metadata derived from config — so this has to be
proven against the real saver, not assumed.
"""

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel


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

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    graph = builder.compile(checkpointer=SqliteSaver(conn))

    result = graph.invoke(
        _State(),
        {"configurable": {"thread_id": "spike-1", "probe": _NotSerialisable()}},
    )

    assert result["seen"] == "alive"
    conn.close()
