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


# Summing two snapshots ----------------------------------------------------
#
# A diagnosis is driven in two passes: the first stops at the clarifying-question
# interrupt, the second resumes and finishes it. Each pass has its own collector, so the
# run's real cost is the sum of two snapshots and nothing else can produce it.


def test_two_snapshots_add_their_tokens():
    first = UsageSnapshot(prompt_tokens=100, completion_tokens=20, cost_usd=None)
    second = UsageSnapshot(prompt_tokens=5, completion_tokens=3, cost_usd=None)

    total = first.plus(second)

    assert total == UsageSnapshot(prompt_tokens=105, completion_tokens=23, cost_usd=None)
    assert total.total_tokens == 128


def test_adding_snapshots_sums_the_costs_that_were_reported():
    first = UsageSnapshot(prompt_tokens=100, completion_tokens=20, cost_usd=0.004)
    second = UsageSnapshot(prompt_tokens=5, completion_tokens=3, cost_usd=0.001)

    assert first.plus(second).cost_usd == 0.005


def test_adding_a_costless_snapshot_keeps_the_cost_that_was_reported():
    """Follows the same rule as one collector seeing partial cost reporting: sum what was
    seen rather than discarding it, because the tokens are exact either way."""
    measured = UsageSnapshot(prompt_tokens=100, completion_tokens=20, cost_usd=0.004)
    costless = UsageSnapshot(prompt_tokens=5, completion_tokens=3, cost_usd=None)

    assert measured.plus(costless).cost_usd == 0.004
    assert costless.plus(measured).cost_usd == 0.004


def test_adding_two_costless_snapshots_reports_no_cost():
    """Never a fabricated $0.00: nothing reported a cost, so there is no cost to report."""
    first = UsageSnapshot(prompt_tokens=100, completion_tokens=20, cost_usd=None)
    second = UsageSnapshot(prompt_tokens=5, completion_tokens=3, cost_usd=None)

    assert first.plus(second).cost_usd is None


def test_adding_nothing_returns_the_snapshot_unchanged():
    """``None`` is what a pass that reported no usage produces, and it is the common case
    for the first pass of a run whose provider reported nothing."""
    only = UsageSnapshot(prompt_tokens=100, completion_tokens=20, cost_usd=0.004)

    assert only.plus(None) == only
