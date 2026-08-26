"""The harness can still build what the graph needs.

`eval/run_eval.py` constructs `Deps` by hand rather than through `agent.wiring.build_deps`,
because a harness run wires several things differently — scripted gate and vision models per
case, an in-memory checkpointer, a fixed profile block. That is the right trade and it has a
cost: a field added to `Deps` reaches the application through `build_deps` and reaches the
harness through nobody, so the harness breaks at runtime and every test goes on passing.

Which is exactly what happened when the second identification was added. The harness is
excluded from coverage (`M1`), its own tests drive `run_case` with fixtures rather than
`run_eval`'s wiring, and nothing anywhere constructed the real thing. It would have been
found by running the harness — a command that costs money and minutes, and is therefore run
rarely, which is the worst possible detector.

This compares the two by name. It cannot check that a value is *sensible*, only that one was
supplied; the sensible-ness of this particular one — an identifier that returns nothing — is
argued at the call site.
"""

import ast
import pathlib

from agent.deps import Deps

RUN_EVAL = pathlib.Path("eval/run_eval.py")


def _fields_supplied_to_deps() -> set[str]:
    """The keyword names in `run_eval`'s one `Deps(...)` call."""
    tree = ast.parse(RUN_EVAL.read_text(encoding="utf-8"))

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Deps"
    ]
    assert len(calls) == 1, f"expected one Deps(...) in {RUN_EVAL}, found {len(calls)}"

    return {keyword.arg for keyword in calls[0].keywords if keyword.arg}


def test_the_harness_supplies_every_dependency_the_graph_needs():
    missing = set(Deps.__dataclass_fields__) - _fields_supplied_to_deps()

    assert missing == set(), (
        f"{RUN_EVAL} does not supply {sorted(missing)}. The evaluation harness builds Deps "
        "by hand, so a new field has to be added there too — otherwise the harness raises "
        "on its next run, which is a command nobody runs often enough to find it."
    )


def test_it_supplies_nothing_that_is_not_a_dependency():
    """The other direction: a field renamed in `Deps` leaves a stale keyword behind, which
    fails with a `TypeError` at exactly the same unhelpful moment."""
    unknown = _fields_supplied_to_deps() - set(Deps.__dataclass_fields__)

    assert unknown == set()
