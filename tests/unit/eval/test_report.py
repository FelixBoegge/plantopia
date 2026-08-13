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
    "ragas_counts": {
        "context_precision": {"scored": 28, "total": 28},
        "context_recall": {"scored": 28, "total": 28},
        "faithfulness": {"scored": 28, "total": 28},
        "answer_relevancy": {"scored": 0, "total": 28},
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


def test_a_fully_scored_ragas_metric_has_no_redundant_note():
    """A metric that scored every submitted case must not be cluttered with a
    count note — that's the common case and should read as a plain percentage."""
    report = render_report(RESULTS)

    faithfulness_line = next(line for line in report.splitlines() if "Faithfulness" in line)
    assert "scored" not in faithfulness_line.lower()
    assert "90.0%" in faithfulness_line


def test_a_fully_nan_ragas_metric_discloses_its_zero_count():
    """Spec §5: the report must say how many cells failed, not just that the mean
    is missing. A metric that scored nothing still renders as 'not measured' —
    never 0.0% — but the count says zero of how many were submitted."""
    report = render_report(RESULTS)

    relevancy_line = next(line for line in report.splitlines() if "Answer relevancy" in line)
    assert "not measured" in relevancy_line.lower()
    assert "0.0%" not in relevancy_line
    assert "0 of 28" in relevancy_line


def test_a_partially_scored_ragas_metric_states_its_count():
    """The exact scenario the first real run hit: five judge calls failed, Ragas
    turned those cells into NaN, and the mean silently skipped them. The report
    must say the mean came from fewer cases than were submitted."""
    partial = {
        **RESULTS,
        "ragas": {**RESULTS["ragas"], "context_precision": 0.82},
        "ragas_counts": {
            **RESULTS["ragas_counts"],
            "context_precision": {"scored": 23, "total": 28},
        },
    }
    report = render_report(partial)

    precision_line = next(line for line in report.splitlines() if "Context precision" in line)
    assert "82.0%" in precision_line
    assert "23 of 28" in precision_line


def test_missing_ragas_counts_still_renders_a_plain_percentage():
    """Older results files (or a caller that never populated counts) must not
    crash the renderer — fall back to a bare percentage."""
    legacy = {k: v for k, v in RESULTS.items() if k != "ragas_counts"}

    report = render_report(legacy)

    faithfulness_line = next(line for line in report.splitlines() if "Faithfulness" in line)
    assert "90.0%" in faithfulness_line
