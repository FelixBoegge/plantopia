"""Unit tests for the Ragas adapter. The evaluation call itself is not exercised here."""

import pandas as pd
import pytest

import eval.ragas_metrics as ragas_metrics
from eval.harness import CaseRun
from eval.ragas_metrics import METRIC_NAMES, RagasScores, _as_float, evaluate_runs, to_ragas_rows
from knowledge.ingest import Chunk


def _run(**kw) -> CaseRun:
    defaults = {
        "case_id": "a",
        "ground_truth": "overwatering",
        "category": "watering",
        "candidates": ["overwatering"],
        "reasoning": "Wet soil and lower-leaf yellowing.",
        "contexts": ["Overwatering: soil stays wet for days."],
        "questions_asked": ["drainage"],
        "situation": "My plant has these symptoms: yellowing lower leaves.",
        "usage": None,
        "error": None,
    }
    return CaseRun(**{**defaults, **kw})


def _chunk(**kw) -> Chunk:
    defaults = {
        "doc_id": "overwatering",
        "name": "Overwatering",
        "section": "Symptoms",
        "text": "Yellowing leaves, often with soft brown patches. Soil stays wet for days.",
        "category": "water-and-root",
        "transmissible": False,
        "severity": "act_this_week",
    }
    return Chunk(**{**defaults, **kw})


def test_rows_carry_the_four_fields_ragas_needs():
    rows = to_ragas_rows([_run()])

    assert set(rows[0]) == {"user_input", "response", "retrieved_contexts", "reference"}
    assert rows[0]["retrieved_contexts"] == ["Overwatering: soil stays wet for days."]


def test_user_input_is_the_runs_recorded_situation():
    """``user_input`` must carry the case's real situation, not a placeholder
    question — that placeholder was identical across every case (the defect)."""
    run = _run(situation="My plant has these symptoms: crisp brown leaf edges.")

    rows = to_ragas_rows([run])

    assert rows[0]["user_input"] == "My plant has these symptoms: crisp brown leaf edges."


def test_two_different_cases_produce_different_user_input():
    """The defect this replaces: every case fed Ragas an identical, content-free
    question. Two cases with different symptoms must now produce different rows."""
    run_a = _run(
        case_id="a",
        situation="My plant has these symptoms: yellowing lower leaves.",
    )
    run_b = _run(
        case_id="b",
        situation="My plant has these symptoms: crisp brown leaf tips.",
    )

    rows = to_ragas_rows([run_a, run_b])

    assert rows[0]["user_input"] != rows[1]["user_input"]


def test_failed_runs_are_excluded_from_the_rows():
    """A run with no differential has no response to score."""
    rows = to_ragas_rows([_run(), _run(case_id="b", error="boom", reasoning="")])

    assert len(rows) == 1


def test_runs_without_contexts_are_excluded():
    """Context precision over an empty context list is undefined, not zero."""
    rows = to_ragas_rows([_run(contexts=[])])

    assert rows == []


def test_reference_is_built_from_the_ground_truth_documents_name_and_symptoms():
    """``reference`` must read as an answer, not an identifier — the old defect
    fed Ragas the bare slug ``"overwatering"``."""
    corpus = [
        _chunk(section="Symptoms", text="Yellowing leaves and soil that stays wet for days."),
        _chunk(section="Treatment, least-invasive first", text="Stop watering."),
    ]

    rows = to_ragas_rows([_run(ground_truth="overwatering")], corpus)

    assert (
        rows[0]["reference"] == "Overwatering: Yellowing leaves and soil that stays wet for days."
    )


def test_reference_falls_back_to_the_slug_when_the_document_is_missing():
    corpus = [_chunk(doc_id="overwatering", section="Symptoms", text="Wet soil.")]

    rows = to_ragas_rows([_run(ground_truth="some-unindexed-disorder")], corpus)

    assert rows[0]["reference"] == "some-unindexed-disorder"


def test_reference_falls_back_to_the_slug_when_the_symptoms_section_is_missing():
    corpus = [_chunk(doc_id="overwatering", section="Treatment, least-invasive first")]

    rows = to_ragas_rows([_run(ground_truth="overwatering")], corpus)

    assert rows[0]["reference"] == "overwatering"


def test_corpus_lookup_is_built_once_not_per_row(monkeypatch):
    """A many-row call must build the lookup a single time, not once per row —
    the defect this replaces would have re-scanned the corpus per case."""
    calls = []
    original = ragas_metrics._corpus_lookup

    def _counting_lookup(corpus):
        calls.append(1)
        return original(corpus)

    monkeypatch.setattr(ragas_metrics, "_corpus_lookup", _counting_lookup)

    corpus = [_chunk()]
    rows = to_ragas_rows([_run(case_id="a"), _run(case_id="b")], corpus)

    assert len(rows) == 2
    assert len(calls) == 1


def test_evaluation_of_no_scorable_rows_returns_nulls_not_an_error():
    result = evaluate_runs([_run(contexts=[])], llm=object(), embeddings=object())

    assert result.scores == {
        "context_precision": None,
        "context_recall": None,
        "faithfulness": None,
        "answer_relevancy": None,
    }
    assert all(result.counts[name] == {"scored": 0, "total": 0} for name in METRIC_NAMES)


def test_as_float_of_nan_is_none():
    """The NaN guard exists for judge-call timeouts; a NaN score is not a score."""
    assert _as_float(float("nan")) is None


def test_a_raising_evaluate_call_returns_nulls_not_an_error(monkeypatch):
    """A metric failure returns None per metric rather than raising (spec §5):
    one bad metric must not discard the accuracy numbers from a run that cost
    real money."""

    def _boom(*args, **kwargs):
        raise RuntimeError("judge call blew up")

    monkeypatch.setattr(ragas_metrics, "evaluate", _boom)

    result = evaluate_runs([_run()], llm=object(), embeddings=object())

    assert result.scores == {
        "context_precision": None,
        "context_recall": None,
        "faithfulness": None,
        "answer_relevancy": None,
    }
    # One row was submitted before evaluate() blew up, so the count discloses that
    # nothing scored out of the one that was attempted — not "0 of 0", which would
    # read as though nothing was ever submitted.
    assert all(result.counts[name] == {"scored": 0, "total": 1} for name in METRIC_NAMES)


class _FakeResult:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def to_pandas(self) -> pd.DataFrame:
        return self._frame


def test_counts_are_derived_from_non_nan_cells_per_metric(monkeypatch):
    """Ragas swallows individual judge-call failures and turns them into NaN rather
    than raising, so the only way to know a metric silently averaged over fewer cases
    is to count the NaNs (spec §5)."""
    columns = {
        "context_precision": [0.8, 0.9, 0.7],
        "context_recall": [0.5, float("nan"), 0.9],
        "faithfulness": [1.0, 1.0, 1.0],
        "answer_relevancy": [float("nan"), float("nan"), float("nan")],
    }

    def _fake_evaluate(dataset, metrics, **kwargs):
        name = metrics[0].name
        # Every attempt returns the same cells, so the NaNs never resolve.
        values = [v for v in columns[name] if v == v] if len(dataset) < 3 else columns[name]
        return _FakeResult(pd.DataFrame({name: values or [float("nan")] * len(dataset)}))

    monkeypatch.setattr(ragas_metrics, "evaluate", _fake_evaluate)

    result = evaluate_runs(
        [_run(case_id="a"), _run(case_id="b"), _run(case_id="c")],
        llm=object(),
        embeddings=object(),
    )

    assert isinstance(result, RagasScores)
    assert result.counts["context_precision"] == {"scored": 3, "total": 3}
    assert result.counts["faithfulness"] == {"scored": 3, "total": 3}
    assert result.scores["answer_relevancy"] is None
    assert result.counts["answer_relevancy"] == {"scored": 0, "total": 3}


def test_a_cell_that_comes_back_nan_is_retried(monkeypatch):
    """The failures are transport-level — a probe caught openai.APIConnectionError
    under concurrency, not a refusal — so the same cell submitted again usually
    succeeds. Only the cells that failed are re-submitted; paying for the whole
    metric again would multiply the cost of an evaluation that already runs into
    dollars.
    """
    submissions: list[tuple[str, int]] = []

    def _fake_evaluate(dataset, metrics, **kwargs):
        name = metrics[0].name
        rows = len(dataset)
        submissions.append((name, rows))
        if name != "faithfulness":
            return _FakeResult(pd.DataFrame({name: [1.0] * rows}))
        first_attempt = sum(1 for n, _ in submissions if n == name) == 1
        values = [0.5, float("nan")] if first_attempt else [0.9]
        return _FakeResult(pd.DataFrame({name: values}))

    monkeypatch.setattr(ragas_metrics, "evaluate", _fake_evaluate)

    result = evaluate_runs(
        [_run(case_id="a"), _run(case_id="b")], llm=object(), embeddings=object()
    )

    assert result.counts["faithfulness"] == {"scored": 2, "total": 2}
    assert result.scores["faithfulness"] == pytest.approx((0.5 + 0.9) / 2)
    assert ("faithfulness", 1) in submissions, "the retry must re-submit only the failed cell"


def test_each_metric_is_scored_in_its_own_call(monkeypatch):
    """One evaluate() call per metric, not one call carrying all four.

    The previous shape put roughly 280 judge calls for 28 cases into a single
    long-running call, where connection failures accumulated across the whole run
    and every metric lost most of its cells.
    """
    seen: list[tuple[str, ...]] = []

    def _fake_evaluate(dataset, metrics, **kwargs):
        seen.append(tuple(m.name for m in metrics))
        return _FakeResult(pd.DataFrame({metrics[0].name: [1.0] * len(dataset)}))

    monkeypatch.setattr(ragas_metrics, "evaluate", _fake_evaluate)

    evaluate_runs([_run()], llm=object(), embeddings=object())

    assert seen == [(name,) for name in METRIC_NAMES]


def test_one_metric_collapsing_does_not_cost_the_others(monkeypatch):
    """A metric that raises outright loses its own column and nothing else — the
    accuracy numbers from a run that cost real money must survive it (spec §5)."""

    def _fake_evaluate(dataset, metrics, **kwargs):
        name = metrics[0].name
        if name == "context_precision":
            raise RuntimeError("judge call blew up")
        return _FakeResult(pd.DataFrame({name: [0.75] * len(dataset)}))

    monkeypatch.setattr(ragas_metrics, "evaluate", _fake_evaluate)

    result = evaluate_runs([_run()], llm=object(), embeddings=object())

    assert result.scores["context_precision"] is None
    assert result.counts["context_precision"] == {"scored": 0, "total": 1}
    assert result.scores["faithfulness"] == pytest.approx(0.75)
    assert result.counts["faithfulness"] == {"scored": 1, "total": 1}
