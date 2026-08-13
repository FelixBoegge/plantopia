"""UI tests for the Evaluation page."""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui

# AppTest.from_file resolves a relative path against the calling file's directory,
# not the working directory — so this must be absolute to run from anywhere.
_EVALUATION_PAGE = Path(__file__).resolve().parent.parent.parent / "ui" / "pages" / "evaluation.py"


def _write_results(directory, payload) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "2026-08-13T10-00-00+00-00.json").write_text(json.dumps(payload), encoding="utf-8")


def _payload() -> dict:
    return {
        "generated_at": "2026-08-13T10:00:00+00:00",
        "provenance": {
            "reasoning_model": "openai/gpt-4o",
            "vision_model": "scripted",
            "embedding_model": "openai/text-embedding-3-small",
            "temperature": 0.2,
            "corpus_documents": 43,
            "golden_set_size": 28,
        },
        "accuracy": {
            "top1": 0.75,
            "top3": 0.89,
            "scored": 28,
            "failed": 1,
            "by_category": {"watering": {"top1": 1.0, "top3": 1.0, "scored": 4}},
        },
        "ragas": {
            "context_precision": 0.81,
            "context_recall": 0.77,
            "faithfulness": 0.9,
            "answer_relevancy": None,
        },
        "stability": {
            "top1_agreement": 0.6,
            "candidate_churn": 0.42,
            "question_drift": 0.15,
            "cases": 8,
            "runs_per_case": 5.0,
        },
        "near_misses": 3,
    }


def test_the_empty_state_names_the_command(tmp_path, monkeypatch):
    """No traceback when nothing has been run yet (spec §5)."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("PLANTOPIA_EVAL_RESULTS_DIR", str(tmp_path / "missing"))
    app = AppTest.from_file(str(_EVALUATION_PAGE), default_timeout=30).run()

    assert not app.exception
    assert any("eval.run_eval" in info.value for info in app.info)


def test_headline_metrics_render(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    results_dir = tmp_path / "results"
    _write_results(results_dir, _payload())
    monkeypatch.setenv("PLANTOPIA_EVAL_RESULTS_DIR", str(results_dir))

    app = AppTest.from_file(str(_EVALUATION_PAGE), default_timeout=30).run()

    assert not app.exception
    assert any("75" in str(metric.value) for metric in app.metric)


def test_the_vision_caveat_is_shown(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    results_dir = tmp_path / "results"
    _write_results(results_dir, _payload())
    monkeypatch.setenv("PLANTOPIA_EVAL_RESULTS_DIR", str(results_dir))

    app = AppTest.from_file(str(_EVALUATION_PAGE), default_timeout=30).run()

    body = " ".join(m.value for m in app.markdown)
    assert "vision" in body.lower()
