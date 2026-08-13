"""Ragas metrics over completed case runs.

Isolated from ``eval/metrics.py`` so that accuracy and stability scoring stays pure
and offline. Everything here needs a judge model and an embedder, which means a
network call and money.

Both come from the project's existing factories, so this needs no model access the
application does not already have: the reasoning tier and the embedding model are
both verified reachable on the restricted key (spec §3.5).
"""

import logging
import sys
import types
from typing import Any

from eval.harness import CaseRun

logger = logging.getLogger(__name__)


def _shim_legacy_vertexai() -> None:
    """ragas (<=0.4.x) imports legacy Vertex AI classes that langchain-community
    v0.4+ removed. They are only used for isinstance checks on GCP models we
    never pass, so empty stubs keep ragas importable next to LangChain v1."""
    name = "langchain_community.chat_models.vertexai"
    if name not in sys.modules:
        stub = types.ModuleType(name)
        stub.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules[name] = stub
    import langchain_community.llms as llms_mod

    if not hasattr(llms_mod, "VertexAI"):
        llms_mod.VertexAI = type("VertexAI", (), {})


_shim_legacy_vertexai()

from ragas import EvaluationDataset, evaluate  # noqa: E402
from ragas.metrics import (  # noqa: E402
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.run_config import RunConfig  # noqa: E402

METRIC_NAMES = ("context_precision", "context_recall", "faithfulness", "answer_relevancy")


def to_ragas_rows(runs: list[CaseRun]) -> list[dict[str, Any]]:
    """Map completed runs to Ragas' evaluation-sample shape.

    Runs that failed, or that retrieved nothing, are excluded rather than scored as
    zero: context precision over an empty context list is undefined, and a zero
    would be indistinguishable from genuinely bad retrieval.
    """
    return [
        {
            # What the "user" effectively asked: the situation, as the case states it.
            "user_input": _situation(run),
            "response": run.reasoning,
            "retrieved_contexts": list(run.contexts),
            "reference": run.ground_truth,
        }
        for run in runs
        if run.error is None and run.reasoning and run.contexts
    ]


def _situation(run: CaseRun) -> str:
    questions = ", ".join(run.questions_asked) or "none"
    return f"What is wrong with this plant? Clarifying questions asked: {questions}."


def evaluate_runs(
    runs: list[CaseRun], *, llm: Any = None, embeddings: Any = None
) -> dict[str, float | None]:
    """Score runs with Ragas, returning ``None`` for any metric that could not run.

    A metric failure is recorded rather than raised: one metric erroring must not
    discard the accuracy numbers from a run that cost real money (spec §5).
    """
    rows = to_ragas_rows(runs)
    if not rows:
        logger.warning("no scorable rows: every run failed or retrieved nothing")
        return dict.fromkeys(METRIC_NAMES)

    try:
        result = evaluate(
            EvaluationDataset.from_list(rows),
            metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
            llm=llm,
            embeddings=embeddings,
            # OpenRouter's latency spikes exceed Ragas's 180-second default under its
            # default 16-way concurrency, and the result is NaN cells rather than an
            # error. Fewer workers and a longer timeout avoid that.
            run_config=RunConfig(timeout=300, max_workers=4),
        )
        scores = result.to_pandas().mean(numeric_only=True).to_dict()
        return {name: _as_float(scores.get(name)) for name in METRIC_NAMES}
    except Exception as exc:  # noqa: BLE001 — a metric failure is data, not a crash
        logger.warning("ragas evaluation failed: %s", exc)
        return dict.fromkeys(METRIC_NAMES)


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number  # NaN check
