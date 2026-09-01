"""What a client is told a run is doing.

The map has to be total, and that is the whole test. A node added without an entry here
would otherwise either leak its own name to a client or produce an event nobody can render
— and the moment it matters is exactly the moment somebody forgot.
"""

from core.config import Settings
from runs import steps
from tests.secrets import TEST_JWT_SECRET


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET, **overrides
    )


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


def test_a_model_step_names_the_configured_model():
    """Not a hardcoded string: swapping the model in settings has to change what the screen
    says, or the screen is lying the first time somebody swaps one."""
    resolved = steps.calls_for("assess_symptoms", _settings(vision_model="acme/see-1"))

    assert resolved == "acme/see-1 via OpenRouter"


def test_a_step_that_uses_two_things_names_both_in_order():
    resolved = steps.calls_for("identify_plant", _settings(vision_model="acme/see-1"))

    assert resolved == "acme/see-1 via OpenRouter, then Pl@ntNet"


def test_a_service_step_names_the_service():
    assert steps.calls_for("enrich", _settings()) == "the disorder reference, then Open-Meteo"


def test_a_step_that_calls_nothing_says_nothing():
    """`persist` writes rows. Inventing a value for it would put a sentence on screen that
    describes no work."""
    assert steps.calls_for("persist", _settings()) is None


def test_an_unmapped_node_says_nothing_rather_than_guessing():
    assert steps.calls_for("a_node_nobody_has_written_yet", _settings()) is None


def test_every_node_that_calls_something_is_a_node_that_has_a_step():
    """Two maps keyed by the same node names, which drift apart silently otherwise."""
    assert set(steps.CALLS) <= set(steps.STEPS)
