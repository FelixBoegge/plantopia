"""The sweeper actually runs, rather than merely existing.

The quota guard was complete, tested and unreached for a whole change. A scheduler nobody
starts is the same shape of mistake, and it is invisible in exactly the same way: every
unit test of the sweeping logic passes whether or not anything calls it.
"""

import threading
import time

from fastapi.testclient import TestClient

from api.main import create_app
from core.config import Settings
from tests.secrets import TEST_JWT_SECRET


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        openrouter_api_key="sk-test",
        jwt_secret=TEST_JWT_SECRET,
        run_sweeper_interval_seconds=5,
        **overrides,
    )


def _thread_names() -> set[str]:
    return {thread.name for thread in threading.enumerate()}


def test_the_application_starts_the_sweeper():
    with TestClient(create_app(_settings())):
        assert "run-sweeper" in _thread_names()


def test_the_sweeper_stops_when_the_application_does():
    """A reload that left one behind per restart would accumulate threads, each holding a
    database session for a moment every minute."""
    with TestClient(create_app(_settings())):
        pass

    deadline = time.monotonic() + 10.0
    while "run-sweeper" in _thread_names() and time.monotonic() < deadline:
        time.sleep(0.05)

    assert "run-sweeper" not in _thread_names()


def test_a_deployment_can_turn_the_sweeper_off():
    """Several processes would each sweep — harmless but wasteful, and the deployment
    change is where that is decided."""
    with TestClient(create_app(_settings(run_sweeper_enabled=False))):
        assert "run-sweeper" not in _thread_names()
