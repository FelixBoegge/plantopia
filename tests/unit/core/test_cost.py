"""Unit tests for per-run token and cost accounting."""

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from core.cost import UsageCollector, UsageSnapshot


def _result(prompt: int, completion: int, cost: float | None = None) -> LLMResult:
    usage = {"prompt_tokens": prompt, "completion_tokens": completion}
    if cost is not None:
        usage["cost"] = cost
    return LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="x"))]],
        llm_output={"token_usage": usage, "model_name": "test"},
    )


def test_snapshot_is_none_before_any_call():
    assert UsageCollector().snapshot() is None


def test_accumulates_tokens_across_calls():
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20))
    collector.on_llm_end(_result(50, 10))

    snapshot = collector.snapshot()
    assert snapshot == UsageSnapshot(prompt_tokens=150, completion_tokens=30, cost_usd=None)
    assert snapshot.total_tokens == 180


def test_accumulates_cost_when_reported():
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20, cost=0.0012))
    collector.on_llm_end(_result(50, 10, cost=0.0003))

    assert collector.snapshot().cost_usd == 0.0015


def test_cost_stays_none_when_never_reported():
    """A provider that omits cost must not produce a fabricated $0.00 (spec §5)."""
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20))

    assert collector.snapshot().cost_usd is None


def test_partial_cost_reporting_still_sums_what_was_seen():
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20, cost=0.001))
    collector.on_llm_end(_result(50, 10))

    assert collector.snapshot().cost_usd == 0.001


def test_falls_back_to_usage_metadata_on_the_message():
    """Some LangChain paths report usage on the message rather than llm_output."""
    message = AIMessage(
        content="x",
        usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
    )
    result = LLMResult(generations=[[ChatGeneration(message=message)]], llm_output=None)

    collector = UsageCollector()
    collector.on_llm_end(result)

    assert collector.snapshot() == UsageSnapshot(
        prompt_tokens=7, completion_tokens=3, cost_usd=None
    )


def test_a_call_reporting_no_usage_at_all_is_ignored():
    result = LLMResult(generations=[[ChatGeneration(message=AIMessage(content="x"))]])

    collector = UsageCollector()
    collector.on_llm_end(result)

    assert collector.snapshot() is None


def test_as_token_usage_is_json_shaped():
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20))

    assert collector.snapshot().as_token_usage() == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    }
