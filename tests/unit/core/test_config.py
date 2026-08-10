"""Tests for application configuration."""

import pytest
from pydantic import ValidationError

from core.config import Settings


def test_settings_reads_required_key_from_env(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    settings = Settings()
    assert settings.openrouter_api_key == "sk-test"


def test_settings_defaults_to_the_openrouter_endpoint(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    assert Settings().openrouter_base_url == "https://openrouter.ai/api/v1"


def test_the_three_model_tiers_are_distinct(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    settings = Settings()
    assert len({settings.gate_model, settings.vision_model, settings.reasoning_model}) == 3


def test_model_tiers_are_overridable_from_the_environment(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("PLANTOPIA_VISION_MODEL", "openai/gpt-4.1")
    assert Settings().vision_model == "openai/gpt-4.1"


def test_settings_raises_when_required_key_missing(monkeypatch):
    monkeypatch.delenv("PLANTOPIA_OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_applies_defaults(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    settings = Settings()
    assert settings.max_clarifying_questions == 4
    assert 0.0 < settings.retrieval_score_threshold < 1.0
    assert settings.tavily_api_key is None


def test_settings_thresholds_must_be_probabilities(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("PLANTOPIA_RETRIEVAL_SCORE_THRESHOLD", "1.5")
    with pytest.raises(ValidationError):
        Settings()


def test_cross_modal_retrieval_is_off_by_default(monkeypatch):
    """No multimodal embedding model is currently reachable, so the path must not
    fire doomed requests on every diagnosis."""
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    assert Settings().multimodal_embeddings is False


def test_cross_modal_retrieval_can_be_enabled(monkeypatch):
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("PLANTOPIA_MULTIMODAL_EMBEDDINGS", "true")
    assert Settings().multimodal_embeddings is True
