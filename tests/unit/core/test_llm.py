"""Tests for the chat-model factory and the test fakes that replace it."""

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from core.config import get_settings
from core.llm import (
    build_chat_model,
    build_embeddings,
    build_gate_model,
    build_reasoning_model,
    build_vision_model,
)
from tests.fakes.chat_models import (
    FailingChatModel,
    ScriptedChatModel,
    ScriptedStructuredModel,
)


class _Answer(BaseModel):
    value: int


def test_build_chat_model_defaults_to_the_reasoning_tier():
    assert build_chat_model().model_name == get_settings().reasoning_model


def test_build_chat_model_honours_override():
    model = build_chat_model(model="some-other-model", temperature=0.0)
    assert model.model_name == "some-other-model"
    assert model.temperature == 0.0


def test_every_model_points_at_openrouter():
    for factory in (build_chat_model, build_reasoning_model, build_vision_model, build_gate_model):
        assert "openrouter.ai" in str(factory().openai_api_base)


def test_the_tiers_resolve_to_their_configured_slugs():
    settings = get_settings()
    assert build_gate_model().model_name == settings.gate_model
    assert build_vision_model().model_name == settings.vision_model
    assert build_reasoning_model().model_name == settings.reasoning_model


def test_embeddings_also_route_through_openrouter():
    embeddings = build_embeddings()
    assert "openrouter.ai" in str(embeddings.openai_api_base)
    assert embeddings.model == get_settings().embedding_model


def test_embeddings_skip_tiktoken_context_checking():
    """An OpenRouter slug is not a name tiktoken recognises."""
    assert build_embeddings().check_embedding_ctx_length is False


def test_scripted_chat_model_returns_responses_in_order():
    model = ScriptedChatModel(["first", "second"])
    assert model.invoke([HumanMessage("x")]).content == "first"
    assert model.invoke([HumanMessage("x")]).content == "second"


def test_scripted_chat_model_raises_when_script_exhausted():
    model = ScriptedChatModel(["only"])
    model.invoke([HumanMessage("x")])
    with pytest.raises(AssertionError, match="script exhausted"):
        model.invoke([HumanMessage("x")])


def test_scripted_structured_model_returns_queued_objects():
    model = ScriptedStructuredModel([_Answer(value=7)])
    bound = model.with_structured_output(_Answer)
    assert bound.invoke([HumanMessage("x")]) == _Answer(value=7)


def test_scripted_structured_model_records_calls():
    model = ScriptedStructuredModel([_Answer(value=1)])
    model.with_structured_output(_Answer).invoke([HumanMessage("hello")])
    assert model.call_count == 1


def test_failing_chat_model_raises():
    model = FailingChatModel(RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        model.invoke([HumanMessage("x")])


def test_models_request_usage_accounting():
    """OpenRouter only reports the credits it charged when asked (spec §2.3)."""
    from core.llm import build_chat_model

    model = build_chat_model(model="test/model")

    assert model.extra_body["usage"] == {"include": True}


def test_provider_routing_restriction_is_preserved():
    """The require_parameters guard must survive alongside the usage flag."""
    from core.llm import build_chat_model

    model = build_chat_model(model="test/model")

    assert model.extra_body["provider"] == {"require_parameters": True}
