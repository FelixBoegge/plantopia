"""Unit tests for the Ragas adapter. The evaluation call itself is not exercised here."""

import pandas as pd
import pytest

import eval.ragas_metrics as ragas_metrics
from eval.harness import CaseRun
from eval.ragas_metrics import METRIC_NAMES, RagasScores, _as_float, evaluate_runs, to_ragas_rows


def _run(**kw) -> CaseRun:
    defaults = {
        "case_id": "a",
        "ground_truth": "overwatering",
        "category": "watering",
        "candidates": ["overwatering"],
        "reasoning": "Wet soil and lower-leaf yellowing.",
        "contexts": ["Overwatering: soil stays wet for days."],
        "questions_asked": ["drainage"],
        "usage": None,
        "error": None,
    }
    return CaseRun(**{**defaults, **kw})


def test_rows_carry_the_four_fields_ragas_needs():
    rows = to_ragas_rows([_run()])

    assert set(rows[0]) == {"user_input", "response", "retrieved_contexts", "reference"}
    assert rows[0]["retrieved_contexts"] == ["Overwatering: soil stays wet for days."]
    assert rows[0]["reference"] == "overwatering"


def test_failed_runs_are_excluded_from_the_rows():
    """A run with no differential has no response to score."""
    rows = to_ragas_rows([_run(), _run(case_id="b", error="boom", reasoning="")])

    assert len(rows) == 1


def test_runs_without_contexts_are_excluded():
    """Context precision over an empty context list is undefined, not zero."""
    rows = to_ragas_rows([_run(contexts=[])])

    assert rows == []


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


def test_counts_are_derived_from_non_nan_cells_per_column():
    """Ragas swallows individual judge-call failures and turns them into NaN rather
    than raising, so the only way to know a metric silently averaged over fewer
    cases is to count the NaNs in its column (spec §5)."""
    frame = pd.DataFrame(
        {
            "context_precision": [0.8, 0.9, 0.7],
            "context_recall": [0.5, float("nan"), 0.9],
            "faithfulness": [1.0, 1.0, 1.0],
            "answer_relevancy": [float("nan"), float("nan"), float("nan")],
        }
    )

    class _FakeResult:
        def to_pandas(self):
            return frame

    result = ragas_metrics._scores_from_result(_FakeResult())

    assert isinstance(result, RagasScores)
    assert result.counts["context_precision"] == {"scored": 3, "total": 3}
    assert result.counts["context_recall"] == {"scored": 2, "total": 3}
    assert result.counts["faithfulness"] == {"scored": 3, "total": 3}
    assert result.counts["answer_relevancy"] == {"scored": 0, "total": 3}

    assert result.scores["context_recall"] == pytest.approx((0.5 + 0.9) / 2)
    assert result.scores["answer_relevancy"] is None
