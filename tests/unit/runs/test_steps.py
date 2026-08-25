"""What a client is told a run is doing.

The map has to be total, and that is the whole test. A node added without an entry here
would otherwise either leak its own name to a client or produce an event nobody can render
— and the moment it matters is exactly the moment somebody forgot.
"""

from runs import steps


def _nodes_of(graph) -> set[str]:
    """Every node name the compiled graph knows about, minus LangGraph's own markers."""
    return {name for name in graph.nodes if not name.startswith("__")}


def test_every_node_in_the_diagnosis_graph_has_a_description(make_deps):
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph

    graph = build_diagnosis_graph(make_deps(), MemorySaver())

    missing = sorted(node for node in _nodes_of(graph) if node not in steps.STEPS)
    assert missing == [], f"these nodes would reach a client unnamed: {missing}"


def test_an_unmapped_node_yields_a_neutral_description():
    """A fallback that leaked the node's own name would leak it exactly when somebody had
    added a node and forgotten this file, which is the only time it would matter."""
    step = steps.step_for("some_node_nobody_mapped")

    assert step is steps.UNKNOWN
    assert "some_node_nobody_mapped" not in step.description
    assert "some_node_nobody_mapped" not in step.id


def test_no_description_contains_an_underscore_style_identifier():
    """A sentence, not a symbol. `identify_plant` rendered in a browser is a client coupled
    to a function name."""
    for node, step in steps.STEPS.items():
        assert node not in step.description, f"{node} leaks its own name"
        assert "_" not in step.description, f"{step.description} reads like an identifier"


def test_step_identifiers_are_stable_and_machine_readable():
    """A client branches on these, so they are as much a contract as a status code."""
    for step in [*steps.STEPS.values(), steps.UNKNOWN]:
        assert step.id
        assert step.id.islower()
        assert " " not in step.id


def test_two_nodes_may_share_a_step():
    """`guard_input` and `quality_check` are one thing to a person looking at a screen.
    Collapsing them is deliberate, not an accident of the table."""
    assert steps.STEPS["guard_input"].id == steps.STEPS["quality_check"].id
