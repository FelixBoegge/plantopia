"""Shared pytest fixtures. Populated as tasks add fixtures."""

from datetime import UTC, datetime

import pytest

from data.db import apply_schema, connect


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    """Every test runs with a dummy API key so Settings never fails to construct."""
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")


@pytest.fixture
def db():
    """In-memory database with the full schema applied."""
    conn = connect(":memory:")
    apply_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def now():
    """A fixed instant. Never use wall-clock time in tests."""
    fixed = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    return lambda: fixed
