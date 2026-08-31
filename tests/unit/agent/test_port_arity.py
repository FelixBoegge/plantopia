"""Every wired lambda can be called the way the graph calls it.

`Deps` declares its ports as `Callable[[...], ...]`. Python does not check that annotation
against what is assigned to it, and every node test supplies its own fake, so a port whose
argument list grows produces a codebase where:

- the node passes the new argument,
- the port's type says it should,
- every unit and graph test passes, because every one of them uses a fake with the new
  signature,
- and both real wirings still hold a lambda with the old one.

That is not hypothetical. `weather` gained a fourth argument and `agent/wiring.py` and
`eval/run_eval.py` both kept three-argument lambdas. Fifteen hundred Python tests passed.
The failure surfaced in a browser run, as a diagnosis that died at the enrich step with
`TypeError: <lambda>() takes from 2 to 3 positional arguments but 4 were given`.

`tests/unit/eval/test_harness_wiring.py` compares field *names* and so cannot see this:
`weather` was supplied by both files, and supplied wrongly by both.

Checked syntactically rather than by building the real `Deps`, because building it
constructs models that reach the network. A lambda's argument list is a syntactic fact, and
the syntax is all this needs.
"""

import ast
import pathlib
import typing

import pytest

from agent.deps import Deps

# Both files that construct `Deps`: the application's wiring, and the evaluation harness's —
# the second being the one nothing else executes until somebody spends money on a run.
WIRINGS = [pathlib.Path("agent/wiring.py"), pathlib.Path("eval/run_eval.py")]


def _positional_count(annotation) -> int | None:
    """How many positional arguments a `Callable[[...], ...]` annotation declares.

    `None` for anything that is not one — a model, a repository, a plain value — which is
    most of `Deps` and none of this test's business.
    """
    if not str(annotation).startswith(("collections.abc.Callable", "typing.Callable")):
        return None

    arguments = typing.get_args(annotation)
    if not arguments or not isinstance(arguments[0], list):
        return None
    return len(arguments[0])


def _ports() -> dict[str, int]:
    """The `Deps` fields that are callables, with the arity each declares."""
    hints = typing.get_type_hints(Deps)
    return {
        name: count
        for name in Deps.__dataclass_fields__
        if (count := _positional_count(hints[name])) is not None
    }


def _lambdas(path: pathlib.Path) -> dict[str, ast.Lambda]:
    """The keyword arguments of this file's one `Deps(...)` call that are lambdas.

    Anything that is not a lambda — a repository, a bound method, a module-level function —
    is left alone. Those are objects with signatures checked wherever they are defined; a
    lambda written inline at the call site is checked nowhere else at all.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Deps"
    ]
    assert len(calls) == 1, f"expected one Deps(...) in {path}, found {len(calls)}"

    return {
        keyword.arg: keyword.value
        for keyword in calls[0].keywords
        if keyword.arg and isinstance(keyword.value, ast.Lambda)
    }


def _arity(node: ast.Lambda) -> tuple[int, int]:
    """How many positional arguments the lambda accepts, at least and at most."""
    positional = len(node.args.posonlyargs) + len(node.args.args)
    return positional - len(node.args.defaults), positional


@pytest.mark.parametrize("path", WIRINGS, ids=str)
def test_there_are_lambdas_to_check(path):
    """A guard on the guard. If the parsing above stopped finding either the ports or the
    lambdas, the assertion below would pass over an empty set and say nothing."""
    assert _ports()["weather"] == 4
    assert "weather" in _lambdas(path)


@pytest.mark.parametrize("path", WIRINGS, ids=str)
def test_every_wired_lambda_takes_what_the_port_declares(path):
    ports = _ports()

    wrong = []
    for name, node in _lambdas(path).items():
        declared = ports.get(name)
        if declared is None:
            continue
        required, accepted = _arity(node)
        if accepted < declared or required > declared:
            wrong.append(f"{name}: wired to take {required}-{accepted}, port declares {declared}")

    assert wrong == [], (
        f"{path} wires ports the graph cannot call:\n  "
        + "\n  ".join(wrong)
        + "\nEvery test passes regardless, because every test supplies its own fake. Only a "
        "real run finds this, and for the harness a real run costs money."
    )
