"""Unit tests for optional LangSmith tracing."""

import os

import pytest

from core.config import Settings
from core.tracing import configure_tracing
from tests.secrets import TEST_JWT_SECRET


def _settings(**overrides) -> Settings:
    return Settings(
        openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET, _env_file=None, **overrides
    )


@pytest.fixture(autouse=True)
def _clean_langsmith_env(monkeypatch):
    """``configure_tracing`` sets ``os.environ`` directly — that is the whole point,
    since LangChain's tracer reads process environment variables rather than a
    callback. ``monkeypatch`` only reverts keys it has itself touched, so a test that
    calls ``configure_tracing`` with a real key would otherwise leak
    ``LANGSMITH_TRACING`` / ``LANGSMITH_API_KEY`` / ``LANGSMITH_PROJECT`` into the rest
    of the pytest session. Registering all three with ``monkeypatch.delenv`` here,
    before every test in this module runs, makes monkeypatch adopt them so its
    teardown restores (or deletes) them regardless of what ``configure_tracing``
    wrote directly.
    """
    for key in (
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGSMITH_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_tracing_is_disabled_without_a_key():
    """A fresh clone with no LangSmith account must run unchanged (spec §2.4)."""
    assert configure_tracing(_settings()) is False
    assert "LANGSMITH_TRACING" not in os.environ


def test_tracing_is_enabled_with_a_key():
    enabled = configure_tracing(_settings(langsmith_api_key="ls-test"))

    assert enabled is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "ls-test"
    assert os.environ["LANGSMITH_PROJECT"] == "plantopia"


def test_project_name_is_configurable():
    configure_tracing(_settings(langsmith_api_key="ls-test", langsmith_project="phase-3"))

    assert os.environ["LANGSMITH_PROJECT"] == "phase-3"


def test_a_blank_key_counts_as_absent():
    """An empty PLANTOPIA_LANGSMITH_API_KEY= line in .env must not enable tracing."""
    assert configure_tracing(_settings(langsmith_api_key="   ")) is False
    assert "LANGSMITH_TRACING" not in os.environ


def test_endpoint_is_exported_when_key_and_endpoint_are_both_configured():
    """A region-scoped key (e.g. an EU workspace) needs the matching host, or every
    upload 403s against the US default while the app reports tracing as enabled."""
    configure_tracing(
        _settings(
            langsmith_api_key="ls-test",
            langsmith_endpoint="https://eu.api.smith.langchain.com",
        )
    )

    assert os.environ["LANGSMITH_ENDPOINT"] == "https://eu.api.smith.langchain.com"


def test_endpoint_is_left_unset_when_not_configured():
    """No configured endpoint must mean the SDK's own default applies, not a
    hardcoded US host — so a future SDK default change is inherited for free."""
    configure_tracing(_settings(langsmith_api_key="ls-test"))

    assert "LANGSMITH_ENDPOINT" not in os.environ


def test_a_blank_endpoint_counts_as_absent():
    """An empty PLANTOPIA_LANGSMITH_ENDPOINT= line in .env must not set the variable,
    exactly like a blank API key."""
    configure_tracing(_settings(langsmith_api_key="ls-test", langsmith_endpoint="   "))

    assert "LANGSMITH_ENDPOINT" not in os.environ


def test_endpoint_is_not_exported_without_a_key():
    """No key at all disables tracing entirely — the endpoint must not leak out on
    its own, and configure_tracing must still report tracing as off."""
    enabled = configure_tracing(_settings(langsmith_endpoint="https://eu.api.smith.langchain.com"))

    assert enabled is False
    assert "LANGSMITH_ENDPOINT" not in os.environ
