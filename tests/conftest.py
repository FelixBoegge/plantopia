"""Shared pytest fixtures. Populated as tasks add fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    """Every test runs with a dummy API key so Settings never fails to construct."""
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
