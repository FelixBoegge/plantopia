"""Unit tests for accuracy and stability scoring. Pure functions, no network."""

import pytest

from agent.nodes.context import (
    ALWAYS_ASK_KEYS,
    DRAINAGE_QUESTION,
    LOCATION_KEY,
    WATERING_QUESTION,
)
from core.cost import UsageSnapshot
from eval.cases import GoldenCase
from eval.harness import CaseRun
from eval.metrics import accuracy, near_misses, stability, top1_hit, top3_hit, total_usage


def _run(case_id: str, candidates: list[str], truth: str = "overwatering", **kw) -> CaseRun:
    return CaseRun(
        case_id=case_id,
        ground_truth=truth,
        category=kw.pop("category", "watering"),
        candidates=candidates,
        reasoning="because",
        contexts=[],
        questions_asked=kw.pop("questions_asked", []),
        situation=kw.pop("situation", "irrelevant to this metric"),
        usage=kw.pop("usage", None),
        error=kw.pop("error", None),
    )


def _case(case_id: str, also_acceptable: list[str] | None = None, truth: str = "overwatering"):
    return GoldenCase.model_validate(
        {
            "id": case_id,
            "category": "watering",
            "plant": {"name": "Test plant"},
            "symptoms": {
                "overall_vigor": "declining",
                "symptoms": [
                    {"description": "wilting", "position": "whole_leaf", "severity": "monitor"}
                ],
            },
            "ground_truth": truth,
            "also_acceptable": also_acceptable or [],
        }
    )


def test_top1_hit_on_an_exact_match():
    assert top1_hit(_run("a", ["overwatering", "root-rot"])) is True


def test_top1_miss_when_the_truth_is_second():
    assert top1_hit(_run("a", ["root-rot", "overwatering"])) is False


def test_top3_hit_when_the_truth_is_third():
    assert top3_hit(_run("a", ["rust", "root-rot", "overwatering"])) is True


def test_top3_miss_when_the_truth_is_fourth():
    assert top3_hit(_run("a", ["rust", "root-rot", "aphids", "overwatering"])) is False


def test_an_empty_differential_is_a_miss():
    assert top1_hit(_run("a", [])) is False
    assert top3_hit(_run("a", [])) is False


def test_top1_hit_accepts_an_underscore_variant_of_the_ground_truth():
    """Gate 1: the model emitted `insufficient_light` where the corpus slug is
    `insufficient-light`, scoring a correct diagnosis as a miss."""
    assert top1_hit(_run("a", ["insufficient_light"], truth="insufficient-light")) is True


def test_top3_hit_accepts_an_underscore_variant_in_third_place():
    assert (
        top3_hit(_run("a", ["rust", "root-rot", "insufficient_light"], truth="insufficient-light"))
        is True
    )


def test_top1_hit_ignores_case_and_surrounding_whitespace():
    assert top1_hit(_run("a", [" Insufficient-Light \n"], truth="insufficient-light")) is True


def test_top1_hit_still_misses_a_genuinely_different_disorder():
    """The normalisation must not make everything match."""
    assert top1_hit(_run("a", ["overwatering"], truth="insufficient-light")) is False


def test_near_misses_counts_a_normalised_also_acceptable_match():
    runs = [_run("a", ["root_rot"], truth="overwatering")]
    cases = {"a": _case("a", also_acceptable=["root-rot"], truth="overwatering")}

    assert near_misses(runs, cases) == 1


def test_accuracy_aggregates_and_breaks_down_by_category():
    runs = [
        _run("a", ["overwatering"], category="watering"),
        _run("b", ["root-rot"], category="watering"),
        _run("c", ["aphids"], truth="aphids", category="pest"),
    ]

    report = accuracy(runs)

    assert report.top1 == 2 / 3
    assert report.by_category["watering"].top1 == 0.5
    assert report.by_category["pest"].top1 == 1.0


def test_failed_runs_are_counted_but_never_silently_dropped():
    """Averaging over survivors would flatter the result (spec §5)."""
    runs = [_run("a", ["overwatering"]), _run("b", [], error="boom")]

    report = accuracy(runs)

    assert report.failed == 1
    assert report.scored == 2
    assert report.top1 == 0.5


def test_accuracy_of_no_runs_is_zero_not_a_division_error():
    report = accuracy([])
    assert report.top1 == 0.0
    assert report.scored == 0


def test_stability_is_one_when_every_repeat_agrees():
    runs = {"a": [_run("a", ["overwatering"]) for _ in range(5)]}

    report = stability(runs)

    assert report.top1_agreement == 1.0
    assert report.candidate_churn == 0.0


def test_stability_falls_when_the_top_candidate_moves():
    runs = {
        "a": [
            _run("a", ["overwatering", "root-rot"]),
            _run("a", ["overwatering", "root-rot"]),
            _run("a", ["rust", "root-rot"]),
        ]
    }

    report = stability(runs)

    assert report.top1_agreement == 2 / 3
    assert report.candidate_churn > 0.0


def test_churn_is_total_when_candidate_sets_are_disjoint():
    """The recorded finding: Root Rot 60% one run, Rust 60% the next."""
    runs = {
        "a": [
            _run("a", ["root-rot", "insufficient-light", "magnesium-deficiency"]),
            _run("a", ["rust", "fungal-leaf-spot", "natural-senescence"]),
        ]
    }

    report = stability(runs)

    assert report.candidate_churn == 1.0
    assert report.top1_agreement == 0.5


def test_question_drift_is_reported_separately_from_variance():
    """Two runs that differ only in which model-chosen question was asked, on top
    of the same mandatory pair, still register drift."""
    runs = {
        "a": [
            _run(
                "a",
                ["overwatering"],
                questions_asked=[WATERING_QUESTION.key, DRAINAGE_QUESTION.key, "light_hours"],
            ),
            _run(
                "a",
                ["overwatering"],
                questions_asked=[WATERING_QUESTION.key, DRAINAGE_QUESTION.key, "humidity"],
            ),
        ]
    }

    report = stability(runs)

    assert report.question_drift > 0.0


def test_question_drift_excludes_deterministic_mandatory_questions():
    """``watering``/``drainage`` (``ALWAYS_ASK_KEYS``) and the conditional location
    question are asked on every run of every case, so they must be subtracted before
    Jaccard distance is taken. Two runs whose *only* difference is which model-chosen
    question was asked should register maximal drift, not a dampened partial score:
    with the mandatory keys left in, {drainage, light_hours} vs {drainage, humidity}
    would score 0.67 instead of the true 1.0 disagreement over the model's choice."""
    runs = {
        "a": [
            _run(
                "a",
                ["overwatering"],
                questions_asked=[
                    WATERING_QUESTION.key,
                    DRAINAGE_QUESTION.key,
                    LOCATION_KEY,
                    "light_hours",
                ],
            ),
            _run(
                "a",
                ["overwatering"],
                questions_asked=[
                    WATERING_QUESTION.key,
                    DRAINAGE_QUESTION.key,
                    LOCATION_KEY,
                    "humidity",
                ],
            ),
        ]
    }

    report = stability(runs)

    assert report.question_drift == 1.0


def test_question_drift_is_zero_when_only_deterministic_questions_differ():
    """If the model chose no extra questions at all, differing only in whether the
    conditional location question was asked, the deterministic keys must not count
    toward drift: after exclusion, both runs reduce to the same (empty) set."""
    runs = {
        "a": [
            _run(
                "a",
                ["overwatering"],
                questions_asked=[WATERING_QUESTION.key, DRAINAGE_QUESTION.key],
            ),
            _run(
                "a",
                ["overwatering"],
                questions_asked=[
                    WATERING_QUESTION.key,
                    DRAINAGE_QUESTION.key,
                    LOCATION_KEY,
                ],
            ),
        ]
    }

    report = stability(runs)

    assert report.question_drift == 0.0
    assert ALWAYS_ASK_KEYS  # sanity: the constant this test relies on is non-empty


def test_stability_normalises_separator_variants_before_comparing():
    """Gate 1 recorded `insufficient_light` once against `insufficient-light`
    everywhere else — nondeterministic output formatting, not real disagreement.
    `top1_hit`/`top3_hit` already fold this out via `_normalise_id`; `stability()`
    must apply the same normalisation to its own modal-agreement and churn
    comparisons, or the exact noise the change exists to remove still counts as
    instability here."""
    runs = {
        "a": [
            _run("a", ["insufficient-light"]),
            _run("a", ["insufficient_light"]),
            _run("a", [" Insufficient-Light \n"]),
        ]
    }

    report = stability(runs)

    assert report.top1_agreement == 1.0
    assert report.candidate_churn == 0.0


def test_stability_of_no_cases_is_zero_not_a_division_error():
    report = stability({})
    assert report.top1_agreement == 0.0
    assert report.candidate_churn == 0.0
    assert report.question_drift == 0.0
    assert report.cases == 0


def test_a_failed_run_counts_against_agreement_not_out_of_it():
    """Reviewer scenario: two runs agree on `overwatering`, one fails outright.
    `candidate_churn` already reflects the disagreement via the failed run's empty
    set; `top1_agreement` must count the same failed run in its denominator rather
    than silently excluding it, which would report 2/2 == 1.0 "perfect stability"
    for a case that actually disagreed one time in three."""
    runs = {
        "a": [
            _run("a", ["overwatering"]),
            _run("a", ["overwatering"]),
            _run("a", [], error="boom"),
        ]
    }

    report = stability(runs)

    assert report.top1_agreement == 2 / 3
    assert report.candidate_churn > 0.0


def test_stability_of_a_case_where_every_run_failed_is_zero_not_a_division_error():
    runs = {"a": [_run("a", [], error="boom"), _run("a", [], error="boom")]}

    report = stability(runs)

    assert report.top1_agreement == 0.0
    assert report.candidate_churn == 0.0


def test_near_misses_counts_a_top1_miss_onto_an_also_acceptable_disorder():
    """also_acceptable never feeds top1/top3 scoring (spec §3.5) — the code is the
    better behaviour, a near miss is still a miss — but it is reported separately."""
    runs = [_run("a", ["root-rot"], truth="overwatering")]
    cases = {"a": _case("a", also_acceptable=["root-rot"], truth="overwatering")}

    assert near_misses(runs, cases) == 1


def test_near_misses_excludes_a_top1_hit():
    runs = [_run("a", ["overwatering"], truth="overwatering")]
    cases = {"a": _case("a", also_acceptable=["root-rot"], truth="overwatering")}

    assert near_misses(runs, cases) == 0


def test_near_misses_excludes_a_miss_onto_an_unrelated_disorder():
    runs = [_run("a", ["rust"], truth="overwatering")]
    cases = {"a": _case("a", also_acceptable=["root-rot"], truth="overwatering")}

    assert near_misses(runs, cases) == 0


def test_near_misses_excludes_a_failed_run_with_no_candidates():
    runs = [_run("a", [], truth="overwatering", error="boom")]
    cases = {"a": _case("a", also_acceptable=["root-rot"], truth="overwatering")}

    assert near_misses(runs, cases) == 0


def test_near_misses_sums_across_multiple_cases():
    runs = [
        _run("a", ["root-rot"], truth="overwatering"),
        _run("b", ["overwatering"], truth="root-rot"),
        _run("c", ["overwatering"], truth="overwatering"),
    ]
    cases = {
        "a": _case("a", also_acceptable=["root-rot"], truth="overwatering"),
        "b": _case("b", also_acceptable=["overwatering"], truth="root-rot"),
        "c": _case("c", also_acceptable=["root-rot"], truth="overwatering"),
    }

    assert near_misses(runs, cases) == 2


def test_total_usage_is_none_when_no_run_recorded_any():
    """Mirrors ``UsageCollector.snapshot()``: unmeasured, not a zeroed total that
    would read as a free run."""
    runs = [_run("a", ["overwatering"]), _run("b", ["overwatering"])]

    assert total_usage(runs) is None


def test_total_usage_sums_tokens_and_cost_across_all_runs():
    runs = [
        _run("a", ["overwatering"], usage=UsageSnapshot(100, 50, 0.01)),
        _run("b", ["overwatering"], usage=UsageSnapshot(200, 75, 0.02)),
    ]

    usage = total_usage(runs)

    assert usage.prompt_tokens == 300
    assert usage.completion_tokens == 125
    assert usage.cost_usd == pytest.approx(0.03)


def test_total_usage_omits_runs_with_no_usage_from_the_sum():
    """A run that failed before any model call reported usage has ``usage=None``;
    it must not zero out the total, and must not raise on a ``None`` attribute
    access."""
    runs = [
        _run("a", ["overwatering"], usage=UsageSnapshot(100, 50, 0.01)),
        _run("b", [], usage=None, error="boom"),
    ]

    usage = total_usage(runs)

    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 50


def test_total_usage_is_none_cost_when_no_run_reported_one():
    """OpenRouter can omit cost even while reporting tokens. The aggregate must
    never fabricate a $0.00."""
    runs = [
        _run("a", ["overwatering"], usage=UsageSnapshot(100, 50, None)),
        _run("b", ["overwatering"], usage=UsageSnapshot(200, 75, None)),
    ]

    usage = total_usage(runs)

    assert usage.prompt_tokens == 300
    assert usage.cost_usd is None
