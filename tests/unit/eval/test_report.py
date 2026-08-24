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
        "profile": "empty",
        "total_token_usage": {
            "prompt_tokens": 120_000,
            "completion_tokens": 45_000,
            "total_tokens": 165_000,
        },
        "total_cost_usd": 3.1416,
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
    "stability_case_ids": ["nitrogen-deficiency-a", "overwatering-b"],
    "near_misses": 3,
}


def _copy() -> dict:
    """A deep-ish copy of RESULTS, so a test can mutate one key safely."""
    import copy

    return copy.deepcopy(RESULTS)


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


def test_the_stability_case_ids_are_named():
    """The subset is alphabetical and undisclosed today — the report must at
    least say which cases it measured, not just how many."""
    report = render_report(RESULTS)

    stability_section = report.split("## Stability")[1]
    assert "nitrogen-deficiency-a" in stability_section
    assert "overwatering-b" in stability_section


def test_missing_stability_case_ids_does_not_crash():
    """Older results files predate this field — must render, just without names."""
    legacy = {k: v for k, v in RESULTS.items() if k != "stability_case_ids"}

    report = render_report(legacy)

    assert "8 cases run 5 times each" in report


def test_total_usage_is_rendered_in_provenance():
    report = render_report(RESULTS)

    provenance_section = report.split("## Headline metrics")[0]
    assert "120,000" in provenance_section
    assert "45,000" in provenance_section
    assert "$3.1416" in provenance_section


def test_total_usage_renders_tokens_only_when_cost_is_none():
    """OpenRouter can omit cost while still reporting tokens. Never a fabricated
    $0.00 — consistent with ``ui/components/cost_badge.py``."""
    no_cost = {
        **RESULTS,
        "provenance": {**RESULTS["provenance"], "total_cost_usd": None},
    }

    report = render_report(no_cost)

    provenance_section = report.split("## Headline metrics")[0]
    assert "120,000" in provenance_section
    assert "$" not in provenance_section


def test_the_profile_is_recorded_in_provenance():
    """A profile is a run-level input (spec §4.3) — the report must say which
    fixture produced the numbers, same as the model or the corpus size."""
    report = render_report(RESULTS)

    provenance_section = report.split("## Headline metrics")[0]
    assert "empty" in provenance_section


def test_a_missing_profile_key_does_not_crash():
    """Older results files predate the --profile flag — must render, just
    without a profile row."""
    legacy = {
        **RESULTS,
        "provenance": {k: v for k, v in RESULTS["provenance"].items() if k != "profile"},
    }

    report = render_report(legacy)

    assert "Golden-set size" in report


def test_total_usage_is_absent_when_never_recorded():
    """An older results file with no usage at all must render cleanly, with no
    usage rows — not a crash and not a fabricated zero."""
    no_usage = {
        **RESULTS,
        "provenance": {
            k: v
            for k, v in RESULTS["provenance"].items()
            if k not in {"total_token_usage", "total_cost_usd"}
        },
    }

    report = render_report(no_usage)

    provenance_section = report.split("## Headline metrics")[0]
    assert "Total tokens" not in provenance_section
    assert "Total cost" not in provenance_section


def test_a_single_near_miss_is_singular():
    """The public artefact's pluralisation defect: ``"1 top-1 misses"`` reads as
    grammatically wrong. A single near miss must render as singular."""
    one_miss = {**RESULTS, "near_misses": 1}

    report = render_report(one_miss)

    assert "1 top-1 miss landed" in report
    assert "1 top-1 misses" not in report


def test_multiple_near_misses_are_plural():
    report = render_report(RESULTS)

    assert "3 top-1 misses landed" in report


def test_zero_near_misses_is_plural():
    """Zero takes the plural in English ("0 misses"), same as the pre-existing
    default when the key is absent."""
    zero_misses = {**RESULTS, "near_misses": 0}

    report = render_report(zero_misses)

    assert "0 top-1 misses landed" in report


class TestRetryDisclosure:
    """ "0 failed" cannot distinguish a run where nothing went wrong from one where
    three cases failed and were rescued, and those are different reports about the same
    pipeline (spec §5's rule that a failure stays visible, applied to a recovered one).
    """

    def test_a_clean_run_says_so_explicitly(self):
        results = _copy()
        results["retried_cases"] = []

        report = render_report(results)

        assert "No case needed a second attempt." in report

    def test_rescued_cases_are_named(self):
        results = _copy()
        results["retried_cases"] = ["aphids-clustered-new-growth-hibiscus", "rust-orange-pustules"]

        report = render_report(results)

        assert "2 cases failed on the first attempt" in report
        assert "`aphids-clustered-new-growth-hibiscus`" in report
        assert "`rust-orange-pustules`" in report

    def test_one_rescued_case_reads_as_singular(self):
        results = _copy()
        results["retried_cases"] = ["rust-orange-pustules"]

        assert "1 case failed on the first attempt" in render_report(results)

    def test_an_older_results_file_says_the_answer_is_unknown(self):
        """Silence would look identical to a clean run, and this field did not always
        exist."""
        results = _copy()
        results.pop("retried_cases", None)

        report = render_report(results)

        assert "predates retry tracking" in report
        assert "No case needed a second attempt." not in report


def test_context_precision_names_the_set_it_was_scored_over():
    """It is scored over the passages similarity ranked, not everything the diagnosis
    read. Runs before hypothesis-driven retrieval used every context, so an unlabelled
    number invites comparing two different denominators."""
    report = render_report(_copy())

    assert "Context precision (ranked passages only)" in report
