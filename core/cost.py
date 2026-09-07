"""Per-run token and cost accounting.

Attached to a graph run as a LangChain callback, so it observes every model call
without any node needing to know it exists — including calls from nodes nobody
remembered to instrument. The alternative, accumulating usage in graph state, was
rejected because it would touch every model-calling node and grow the state that
``M15`` already blames for ~100 MB of checkpoint per diagnosis (spec §2.2).

Cost comes from OpenRouter, which reports the credits it actually charged, rather
than from a configured price table that would go stale silently (spec §2.3).
"""

from dataclasses import dataclass
from threading import Lock
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """What one run cost, as of the moment it was taken."""

    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def as_token_usage(self) -> dict[str, int]:
        """The shape written to ``diagnoses.token_usage_json``."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    def plus(self, other: "UsageSnapshot | None") -> "UsageSnapshot":
        """This snapshot and another, added.

        A run is driven in two passes — the first stops at the clarifying-question
        interrupt, the second resumes and finishes it — and each pass has its own
        collector. So the run's real cost is the sum of two snapshots, and nothing
        smaller than that sum is the truth about what it spent.

        Cost follows the same rule one collector already applies to partial reporting:
        sum what was reported and keep ``None`` only when *nothing* reported a cost.
        A pass whose provider reported no cost therefore lowers how complete the figure
        is without inventing a ``$0.00``, which would read as measurement.
        """
        if other is None:
            return self
        costs = [c for c in (self.cost_usd, other.cost_usd) if c is not None]
        return UsageSnapshot(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            # Rounded on the same grounds as ``UsageCollector.snapshot``: adding
            # per-pass costs accumulates representation noise well below a cent.
            cost_usd=round(sum(costs), 8) if costs else None,
        )


def _cost_of(usage: dict[str, Any]) -> float | None:
    """OpenRouter's reported cost for one call, or ``None`` if it reported none."""
    raw = usage.get("cost")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class UsageCollector(BaseCallbackHandler):
    """Accumulates token counts and cost across every model call in one run.

    **One collector covers one invocation, and a diagnosis is two.** ``start`` pauses at
    the clarifying-question interrupt and ``answer`` resumes it, and the vision and gate
    calls — the expensive ones — all happen in the first. So a single collector's snapshot
    is half a diagnosis, and reading it as the whole undercounts by roughly that much.

    The worker builds one per pass, because a pass is what a worker thread owns and the
    pause between them can last as long as somebody takes to answer. Adding the halves is
    therefore ``runs/worker.py``'s job, not this class's: it persists each pass's snapshot
    on the run and sums them with ``UsageSnapshot.plus`` when the finishing pass records
    the run's usage. That is the only place the whole figure exists.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._cost = 0.0
        self._saw_cost = False
        self._calls = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        extracted = self._extract(response)
        if extracted is None:
            return
        prompt_tokens, completion_tokens, cost = extracted
        with self._lock:
            self._calls += 1
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens
            if cost is not None:
                self._saw_cost = True
                self._cost += cost

    @staticmethod
    def _extract(response: LLMResult) -> tuple[int, int, float | None] | None:
        """Token counts and cost from a result, or ``None`` if it carried neither.

        Two shapes are read because LangChain reports usage in two places depending
        on the path taken: ``llm_output["token_usage"]`` for the OpenAI-compatible
        client, and ``message.usage_metadata`` on the generation itself.
        """
        usage = (response.llm_output or {}).get("token_usage") or {}
        if usage:
            return (
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
                _cost_of(usage),
            )

        for generations in response.generations:
            for generation in generations:
                metadata = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if metadata:
                    return (
                        int(metadata.get("input_tokens", 0)),
                        int(metadata.get("output_tokens", 0)),
                        None,
                    )
        return None

    def snapshot(self) -> UsageSnapshot | None:
        """Usage so far, or ``None`` if no model call reported any.

        ``None`` rather than a zeroed snapshot: unit tests run entirely on scripted
        models that report nothing, and writing zeros would make a diagnosis look
        measured when it was not.
        """
        with self._lock:
            if self._calls == 0:
                return None
            return UsageSnapshot(
                prompt_tokens=self._prompt_tokens,
                completion_tokens=self._completion_tokens,
                # Rounded because floating-point addition of per-call costs
                # accumulates representation noise well below a cent.
                cost_usd=round(self._cost, 8) if self._saw_cost else None,
            )
