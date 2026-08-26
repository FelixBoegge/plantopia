"""The evaluation harness does not go through runs, and must not start to.

This change is not allowed to move diagnostic accuracy. The graph, its nodes, its prompts
and its models are untouched; only what watches them is new. The measurement of that claim
is this: the harness still calls the graph directly, so a change in its numbers would mean
this change reached somewhere it should not have.

If the harness were rewired through `RunService`, its runs would acquire a quota, a
cancellation flag, a sweeper and an event stream — and a score that moved afterwards could
no longer be attributed to the agent rather than to the plumbing.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
HARNESS = ROOT / "eval"

# What the harness must not reach for. Each would put the run machinery between the
# evaluation and the graph it is evaluating.
FORBIDDEN = (
    "RunService",
    "run_service",
    "runs.worker",
    "runs.executor",
    "from runs import",
    "RunRepository",
)


def _sources():
    return [path for path in HARNESS.rglob("*.py") if "__pycache__" not in str(path)]


def test_the_harness_does_not_go_through_the_run_machinery():
    offenders = {}
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        found = [name for name in FORBIDDEN if name in text]
        if found:
            offenders[path.name] = found

    assert offenders == {}, (
        f"the evaluation harness now goes through runs: {offenders}. Its numbers would no "
        "longer be attributable to the agent alone."
    )


def test_the_harness_still_builds_the_graph_itself():
    """The other half. A test that only forbids things passes on an empty directory."""
    text = (HARNESS / "run_eval.py").read_text(encoding="utf-8")

    assert "build_diagnosis_graph" in text


def test_the_harness_uses_the_single_request_chat_path_if_it_uses_chat_at_all():
    """Streaming is for somebody watching. A harness reassembling fragments in order to
    ignore them would be reading a different code path than the one it means to measure.
    """
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        assert "messages/stream" not in text, f"{path.name} uses the streaming chat endpoint"
