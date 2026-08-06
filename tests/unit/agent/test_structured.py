"""Tests for resilient structured-output invocation."""

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, ValidationError

from agent.structured import StructuredOutputFailed, invoke_structured


class _Answer(BaseModel):
    value: int


class _StubModel:
    """Minimal model whose structured runnable raises then succeeds."""

    def __init__(self, outcomes: list) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def with_structured_output(self, schema, **kwargs):
        def _respond(_):
            outcome = self.outcomes[self.calls]
            self.calls += 1
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return RunnableLambda(_respond)


def _validation_error() -> ValidationError:
    try:
        _Answer(value="not an int")
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


def test_returns_the_model_result():
    model = _StubModel([_Answer(value=7)])
    assert invoke_structured(model, _Answer, [HumanMessage("x")]) == _Answer(value=7)


def test_calls_the_model_once_on_success():
    model = _StubModel([_Answer(value=1)])
    invoke_structured(model, _Answer, [HumanMessage("x")])
    assert model.calls == 1


def test_retries_once_after_a_validation_error():
    model = _StubModel([_validation_error(), _Answer(value=3)])
    assert invoke_structured(model, _Answer, [HumanMessage("x")]) == _Answer(value=3)
    assert model.calls == 2


def test_raises_after_exhausting_retries():
    model = _StubModel([_validation_error(), _validation_error()])
    with pytest.raises(StructuredOutputFailed):
        invoke_structured(model, _Answer, [HumanMessage("x")])
    assert model.calls == 2


def test_retries_can_be_disabled():
    model = _StubModel([_validation_error()])
    with pytest.raises(StructuredOutputFailed):
        invoke_structured(model, _Answer, [HumanMessage("x")], retries=0)
    assert model.calls == 1


def test_a_transport_error_is_wrapped_not_retried_forever():
    model = _StubModel([RuntimeError("connection reset"), RuntimeError("connection reset")])
    with pytest.raises(StructuredOutputFailed, match="connection reset"):
        invoke_structured(model, _Answer, [HumanMessage("x")])


def test_the_repair_attempt_receives_the_validation_error():
    model = _StubModel([_validation_error(), _Answer(value=1)])
    invoke_structured(model, _Answer, [HumanMessage("original")])
    assert model.calls == 2
