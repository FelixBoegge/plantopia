"""Unit tests for the Ragas adapter. The evaluation call itself is not exercised here."""

from eval.harness import CaseRun
from eval.ragas_metrics import evaluate_runs, to_ragas_rows


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

    assert result == {
        "context_precision": None,
        "context_recall": None,
        "faithfulness": None,
        "answer_relevancy": None,
    }
