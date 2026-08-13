"""Unit tests for report rendering. Deterministic — no models, no clock."""

from eval.report import render_report

RESULTS = {
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


def test_headline_metrics_appear():
    report = render_report(RESULTS)

    assert "75.0%" in report
    assert "88.9%" in report or "89.0%" in report


def test_provenance_is_recorded():
    """A metrics table without the configuration that produced it is not reproducible."""
    report = render_report(RESULTS)

    assert "openai/gpt-4o" in report
    assert "0.2" in report
    assert "43" in report


def test_a_null_metric_renders_as_not_measured_not_as_zero():
    report = render_report(RESULTS)

    assert "0.0%" not in report.split("Answer relevancy")[1].split("\n")[0]
    assert "not measured" in report.lower()


def test_the_vision_caveat_is_always_present():
    """The golden set injects past vision; the report must say so (spec §3.1)."""
    report = render_report(RESULTS)

    assert "does not measure" in report.lower()
    assert "vision" in report.lower()


def test_failed_cases_are_stated():
    report = render_report(RESULTS)

    assert "1" in report
    assert "failed" in report.lower()


def test_per_category_breakdown_is_rendered():
    report = render_report(RESULTS)

    assert "watering" in report
