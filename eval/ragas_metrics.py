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
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from eval.harness import CaseRun
from knowledge.ingest import Chunk

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
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (  # noqa: E402
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.run_config import RunConfig  # noqa: E402

from core.llm import build_embeddings, build_reasoning_model  # noqa: E402

METRIC_NAMES = ("context_precision", "context_recall", "faithfulness", "answer_relevancy")


@dataclass(frozen=True, slots=True)
class RagasScores:
    """Per-metric Ragas means, alongside how many cells each mean was computed over.

    ``scores`` keeps the shape ``evaluate_runs`` has always returned: a mean, or
    ``None`` if the metric could not be scored at all. ``counts`` is new — it maps
    each metric name to ``{"scored": n, "total": m}``, non-NaN cells out of cells
    submitted to Ragas. Two named fields rather than a plain tuple, so a caller
    reads ``result.scores`` / ``result.counts`` rather than unpacking positionally
    at every use site, and both halves serialise to JSON with no extra work.

    Counts are derived from the per-cell dataframe, not from a separate error
    tally, because Ragas swallows individual judge-call failures internally and
    turns the cell into NaN rather than raising — a NaN cell is the only signal
    that a job failed (spec §5).
    """

    scores: dict[str, float | None]
    counts: dict[str, dict[str, int]]


def _empty_scores(total: int) -> RagasScores:
    """All four metrics unmeasured, e.g. no scorable rows or a raised exception.

    ``total`` is how many rows were actually submitted to Ragas before whatever
    went wrong — 0 when nothing was ever submitted, or ``len(rows)`` when
    ``evaluate()`` itself raised after rows were built. Either way, zero of them
    scored.
    """
    return RagasScores(
        scores=dict.fromkeys(METRIC_NAMES),
        counts={name: {"scored": 0, "total": total} for name in METRIC_NAMES},
    )


def _scores_from_result(result: Any) -> RagasScores:
    """Build ``RagasScores`` from a Ragas ``EvaluationResult``.

    Counts non-NaN cells per metric column directly off the dataframe rather than
    trusting a summary the library provides, because the dataframe is the one
    place a swallowed per-cell failure is still visible.
    """
    frame = result.to_pandas()
    total = len(frame)
    scores: dict[str, float | None] = {}
    counts: dict[str, dict[str, int]] = {}
    for name in METRIC_NAMES:
        if name not in frame.columns:
            scores[name] = None
            counts[name] = {"scored": 0, "total": total}
            continue
        column = frame[name]
        counts[name] = {"scored": int(column.notna().sum()), "total": total}
        scores[name] = _as_float(column.mean())
    return RagasScores(scores=scores, counts=counts)


def judge_llm() -> LangchainLLMWrapper:
    """The reasoning model, wrapped for Ragas's judge-LLM metrics.

    Lives here rather than in ``eval/run_eval.py`` because ``ragas.llms`` is only
    importable once ``_shim_legacy_vertexai`` has run, which happens at this
    module's import time. A caller importing ``ragas.llms.LangchainLLMWrapper``
    directly, before this module, hits the same
    ``ModuleNotFoundError: langchain_community.chat_models.vertexai`` the shim
    exists to avoid — so nothing outside this module should import from
    ``ragas`` directly.
    """
    return LangchainLLMWrapper(build_reasoning_model())


def judge_embeddings() -> LangchainEmbeddingsWrapper:
    """The embedding model, wrapped for Ragas's embedding-based metrics.

    See ``judge_llm`` for why this factory lives here instead of at the call site.
    """
    return LangchainEmbeddingsWrapper(build_embeddings())


def _corpus_lookup(corpus: Sequence[Chunk]) -> dict[str, dict[str, str]]:
    """``doc_id -> {"name": ..., "symptoms": ...}``, built once for the whole call.

    Only the pieces ``_reference`` needs: a document's display name, and its
    ``Symptoms`` section text if it has one. A document without a ``Symptoms``
    chunk simply has no ``"symptoms"`` key, which ``_reference`` treats the same
    as the document being entirely absent.
    """
    lookup: dict[str, dict[str, str]] = {}
    for chunk in corpus:
        entry = lookup.setdefault(chunk.doc_id, {"name": chunk.name})
        if chunk.section == "Symptoms":
            entry["symptoms"] = chunk.text
    return lookup


def _reference(ground_truth: str, lookup: dict[str, dict[str, str]]) -> str:
    """The ground-truth document's name plus its Symptoms text, as a reference answer.

    Falls back to the bare slug — the old behaviour — when the document or its
    ``Symptoms`` section is missing, rather than raising: a golden case referencing
    an unindexed corpus document must not crash a run that cost real money.
    """
    entry = lookup.get(ground_truth)
    if not entry or "symptoms" not in entry:
        return ground_truth
    return f"{entry['name']}: {entry['symptoms']}"


def to_ragas_rows(runs: list[CaseRun], corpus: Sequence[Chunk] = ()) -> list[dict[str, Any]]:
    """Map completed runs to Ragas' evaluation-sample shape.

    Runs that failed, or that retrieved nothing, are excluded rather than scored as
    zero: context precision over an empty context list is undefined, and a zero
    would be indistinguishable from genuinely bad retrieval.

    ``user_input`` is the case's actual situation (symptoms plus the answers given),
    carried on ``CaseRun.situation`` — it varies per case, unlike the placeholder
    question this replaced. ``reference`` is the ground-truth document's name and
    Symptoms text, built from ``corpus`` via one lookup for the whole call rather
    than one load per row.
    """
    lookup = _corpus_lookup(corpus)
    return [
        {
            "user_input": run.situation,
            "response": run.reasoning,
            "retrieved_contexts": list(run.contexts),
            "reference": _reference(run.ground_truth, lookup),
        }
        for run in runs
        if run.error is None and run.reasoning and run.contexts
    ]


def evaluate_runs(
    runs: list[CaseRun],
    *,
    corpus: Sequence[Chunk] = (),
    llm: Any = None,
    embeddings: Any = None,
) -> RagasScores:
    """Score runs with Ragas, returning ``None`` for any metric that could not run.

    A metric failure is recorded rather than raised: one metric erroring must not
    discard the accuracy numbers from a run that cost real money (spec §5). The
    returned counts let a reader tell a complete mean from one that silently
    averaged over fewer cases than were submitted.
    """
    rows = to_ragas_rows(runs, corpus)
    if not rows:
        logger.warning("no scorable rows: every run failed or retrieved nothing")
        return _empty_scores(total=0)

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
        return _scores_from_result(result)
    except Exception as exc:  # noqa: BLE001 — a metric failure is data, not a crash
        logger.warning("ragas evaluation failed: %s", exc)
        return _empty_scores(total=len(rows))


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number  # NaN check
