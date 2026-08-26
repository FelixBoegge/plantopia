"""Tests for application configuration."""

import pytest
from pydantic import ValidationError

from core.config import Settings
from tests.secrets import TEST_JWT_SECRET


def test_settings_reads_required_key_from_env(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    settings = Settings(_env_file=None)
    assert settings.openrouter_api_key == "sk-test"


def test_settings_defaults_to_the_openrouter_endpoint(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    assert Settings(_env_file=None).openrouter_base_url == "https://openrouter.ai/api/v1"


def test_the_three_model_tiers_are_distinct(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    settings = Settings(_env_file=None)
    assert len({settings.gate_model, settings.vision_model, settings.reasoning_model}) == 3


def test_model_tiers_are_overridable_from_the_environment(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("PLANTOPIA_VISION_MODEL", "openai/gpt-4.1")
    assert Settings(_env_file=None).vision_model == "openai/gpt-4.1"


def test_settings_raises_when_required_key_missing(monkeypatch):
    monkeypatch.delenv("PLANTOPIA_OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_applies_defaults(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    settings = Settings(_env_file=None)
    assert settings.max_clarifying_questions == 4
    assert 0.0 < settings.retrieval_score_threshold < 1.0
    assert settings.tavily_api_key is None
    assert settings.plantnet_api_key is None


def test_the_database_url_names_its_driver(monkeypatch):
    """A bare postgresql:// URL resolves to psycopg2, which is not installed — and the
    resulting ImportError says nothing about the URL that caused it."""
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")

    assert Settings(_env_file=None).database_url.startswith("postgresql+psycopg://")


def test_the_database_url_is_overridable_from_the_environment(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv(
        "PLANTOPIA_DATABASE_URL", "postgresql+psycopg://someone@db.example:5432/other"
    )

    assert Settings(_env_file=None).database_url.endswith("db.example:5432/other")


def test_settings_thresholds_must_be_probabilities(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("PLANTOPIA_RETRIEVAL_SCORE_THRESHOLD", "1.5")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cross_modal_retrieval_is_off_by_default(monkeypatch):
    """No multimodal embedding model is currently reachable, so the path must not
    fire doomed requests on every diagnosis."""
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    assert Settings(_env_file=None).multimodal_embeddings is False


def test_cross_modal_retrieval_can_be_enabled(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("PLANTOPIA_MULTIMODAL_EMBEDDINGS", "true")
    assert Settings(_env_file=None).multimodal_embeddings is True


def test_the_jwt_secret_has_no_default(monkeypatch):
    """A generated secret would work perfectly here and log everybody out at random in
    production: every restart invalidates every token issued before it, and the cause
    surfaces long after the change that caused it."""
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.delenv("PLANTOPIA_JWT_SECRET", raising=False)

    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None)


def test_token_lifetimes_have_sane_bounds(monkeypatch):
    """An access token cannot be revoked, so its lifetime is the window a stolen one is
    useful for. A configuration typo should not turn fifteen minutes into a year."""
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("PLANTOPIA_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("PLANTOPIA_ACCESS_TOKEN_MINUTES", "525600")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_spend_limits_are_configurable(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("PLANTOPIA_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("PLANTOPIA_MONTHLY_RUN_ALLOWANCE", "3")
    monkeypatch.setenv("PLANTOPIA_DAILY_SPEND_CAP_USD", "0.5")

    settings = Settings(_env_file=None)

    assert settings.monthly_run_allowance == 3
    assert settings.daily_spend_cap_usd == 0.5


class TestRunSettings:
    """The knobs background runs read, and the one distinction among them that matters."""

    def test_every_run_setting_has_a_default(self):
        """A deployment that sets none of these still starts. Requiring a pool size before
        anything can run would be a required setting with an obvious right answer."""
        settings = Settings(_env_file=None, openrouter_api_key="k", jwt_secret=TEST_JWT_SECRET)

        assert settings.run_pool_size >= 1
        assert settings.run_queue_limit >= 1
        assert settings.run_working_ceiling_minutes >= 1
        assert settings.run_answering_ceiling_minutes >= 1
        assert settings.run_keepalive_seconds >= 1

    def test_the_two_ceilings_are_separately_configurable(self):
        """Waiting for a person is not the same as being stuck. One number would either
        reap live conversations or leave dead runs for hours."""
        settings = Settings(
            _env_file=None,
            openrouter_api_key="k",
            jwt_secret=TEST_JWT_SECRET,
            run_working_ceiling_minutes=3,
            run_answering_ceiling_minutes=180,
        )

        assert settings.run_working_ceiling_minutes == 3
        assert settings.run_answering_ceiling_minutes == 180

    def test_waiting_for_a_person_is_given_longer_than_working_by_default(self):
        """Not a rule the type system can hold, but a default that reads as an accident if
        it is ever inverted."""
        settings = Settings(_env_file=None, openrouter_api_key="k", jwt_secret=TEST_JWT_SECRET)

        assert settings.run_answering_ceiling_minutes > settings.run_working_ceiling_minutes

    def test_a_pool_of_zero_is_refused(self):
        """A pool that cannot run anything would accept runs and never start them."""
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                openrouter_api_key="k",
                jwt_secret=TEST_JWT_SECRET,
                run_pool_size=0,
            )


def test_every_credential_is_named_in_the_example_environment():
    """A key a deployment must supply and cannot guess belongs in `.env.example`.

    The rule is credentials specifically, not every setting: most of `Settings` is tuning
    with a sensible default, and listing all of it would make the example file a second
    copy of the class. A credential is different — nothing can infer it, so a deployment
    that does not know it exists simply runs without it, which is precisely how the
    web-search path spent months unexercised (`U1`).
    """
    import pathlib

    example = pathlib.Path(".env.example").read_text(encoding="utf-8")

    credentials = [
        name
        for name in Settings.model_fields
        if name.endswith("_api_key") or name.endswith("_secret")
    ]
    assert credentials, "the rule found nothing to check, which means the rule is wrong"

    missing = [name for name in credentials if f"PLANTOPIA_{name.upper()}" not in example]
    assert missing == []
