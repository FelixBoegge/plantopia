"""The chat dependency hands the agent the owner the request resolved.

Narrow, and here because it was wrong. ``build_deps`` used to resolve the seeded owner
itself, so the agent read and wrote as that owner while the surrounding request was scoped
to somebody else. It was invisible while everybody *was* the seeded owner, and became a
tenancy hole the moment accounts were real.
"""

import inspect

from agent.wiring import build_deps
from api import dependencies
from tests.people import make_owner


def test_the_agent_runs_as_the_owner_the_request_resolved(db, monkeypatch, api_settings):
    captured = {}

    def _capture_deps(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dependencies, "build_deps", _capture_deps)
    monkeypatch.setattr("agent.checkpoints.build_checkpointer", lambda url: object())
    owner = make_owner(db)

    dependencies.chat_service(db, owner, api_settings)

    assert captured["user_id"] == owner


def test_building_deps_requires_being_told_whose_run_it_is(db, monkeypatch, api_settings):
    """No default. A default here is what let the wrong owner through unnoticed."""
    parameter = inspect.signature(build_deps).parameters["user_id"]

    assert parameter.default is inspect.Parameter.empty
