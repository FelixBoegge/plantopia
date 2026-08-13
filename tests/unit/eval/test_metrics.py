"""Unit tests for accuracy and stability scoring. Pure functions, no network."""

from agent.nodes.context import ALWAYS_ASK_KEYS, LOCATION_QUESTION
from eval.harness import CaseRun
from eval.metrics import accuracy, stability, top1_hit, top3_hit


def _run(case_id: str, candidates: list[str], truth: str = "overwatering", **kw) -> CaseRun:
    return CaseRun(
        case_id=case_id,
        ground_truth=truth,
        category=kw.pop("category", "watering"),
        candidates=candidates,
        reasoning="because",
        contexts=[],
        questions_asked=kw.pop("questions_asked", []),
        usage=None,
        error=kw.pop("error", None),
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
            _run("a", ["overwatering"], questions_asked=["watering", "drainage", "light_hours"]),
            _run("a", ["overwatering"], questions_asked=["watering", "drainage", "humidity"]),
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
                questions_asked=["watering", "drainage", LOCATION_QUESTION.key, "light_hours"],
            ),
            _run(
                "a",
                ["overwatering"],
                questions_asked=["watering", "drainage", LOCATION_QUESTION.key, "humidity"],
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
            _run("a", ["overwatering"], questions_asked=["watering", "drainage"]),
            _run(
                "a",
                ["overwatering"],
                questions_asked=["watering", "drainage", LOCATION_QUESTION.key],
            ),
        ]
    }

    report = stability(runs)

    assert report.question_drift == 0.0
    assert ALWAYS_ASK_KEYS  # sanity: the constant this test relies on is non-empty


def test_stability_of_no_cases_is_zero_not_a_division_error():
    report = stability({})
    assert report.top1_agreement == 0.0
    assert report.candidate_churn == 0.0
    assert report.question_drift == 0.0
    assert report.cases == 0
