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

    Scoped to a *thread*, not to a single ``invoke``: a diagnosis spans two
    invocations (``start`` pauses at the clarifying-question interrupt, ``answer``
    resumes it), and the vision and gate calls — the expensive ones — all happen in
    the first. A per-invocation collector would silently undercount by roughly half.
    ``DiagnosisService`` owns the lifetime; see spec §2.1.
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
