"""Diagnostic accuracy and run-to-run stability.

Pure functions over ``CaseRun`` objects — no network, no models — so the scoring
itself is fully unit-tested. Ragas metrics live in ``eval/ragas_metrics.py``
precisely so that this module stays offline and deterministic.
"""

from dataclasses import dataclass, field
from itertools import combinations

from agent.nodes.context import ALWAYS_ASK_KEYS, LOCATION_QUESTION
from core.cost import UsageSnapshot
from eval.cases import GoldenCase
from eval.harness import CaseRun

# ``questions_asked`` records the complete interrupt payload — the mandatory
# watering/drainage pair plus the conditional location question, in addition to
# whatever the model chose (see ``eval/harness.py``). Those deterministic keys are
# asked on every run of every case, so leaving them in the Jaccard distance dampens
# it toward zero and understates how much the model's own question choice actually
# varies (spec §3.4). They are subtracted here, at the metric, from the same
# production constants the questions were generated from — not hardcoded — so this
# stays correct if the mandatory set ever changes.
_DETERMINISTIC_QUESTION_KEYS = ALWAYS_ASK_KEYS | {LOCATION_QUESTION.key}


def _normalise_id(disorder_id: str) -> str:
    """Fold formatting variance out of a disorder id before comparing.

    The model emits ``insufficient_light`` and ``insufficient-light`` for the same
    corpus slug across runs — nondeterministic output formatting, not a systematic
    habit, which made the headline top-3 metric drift run to run for reasons
    unrelated to diagnosis quality (Gate 1). Lowercase, strip, and treat ``_`` and
    ``-`` as equivalent. Nothing else about the id is touched: a genuinely wrong
    disorder must still compare unequal.
    """
    return disorder_id.strip().lower().replace("_", "-")


def _accepted(run: CaseRun) -> set[str]:
    """The normalised disorder ids that count as correct for this case.

    Deliberately ``ground_truth`` alone, not ``ground_truth | also_acceptable``: a
    near miss onto a confusable neighbour is still a miss, and it is surfaced
    separately by ``near_misses`` rather than folded into top-1/top-3, which would
    make the headline number too lenient to say anything about ranking (spec §3.5).
    """
    return {_normalise_id(run.ground_truth)}


def top1_hit(run: CaseRun) -> bool:
    """Was the leading candidate the ground truth?"""
    return bool(run.candidates) and _normalise_id(run.candidates[0]) in _accepted(run)


def top3_hit(run: CaseRun) -> bool:
    """Was the ground truth anywhere in the top three?

    Reported alongside top-1 because the gap between them locates the weakness: a
    high top-3 with a mediocre top-1 says ranking is the problem, not retrieval
    (``PLAN.md`` §16).
    """
    return bool(_accepted(run) & {_normalise_id(c) for c in run.candidates[:3]})


@dataclass(frozen=True, slots=True)
class Scores:
    top1: float
    top3: float
    scored: int


@dataclass(frozen=True, slots=True)
class AccuracyReport:
    top1: float
    top3: float
    scored: int
    failed: int
    by_category: dict[str, Scores] = field(default_factory=dict)


def _score(runs: list[CaseRun]) -> Scores:
    if not runs:
        return Scores(top1=0.0, top3=0.0, scored=0)
    return Scores(
        top1=sum(top1_hit(run) for run in runs) / len(runs),
        top3=sum(top3_hit(run) for run in runs) / len(runs),
        scored=len(runs),
    )


def accuracy(runs: list[CaseRun]) -> AccuracyReport:
    """Overall and per-category accuracy.

    Failed runs stay in the denominator. Averaging over the survivors would report
    a better number for a worse run, which is the opposite of what an evaluation is
    for (spec §5).
    """
    overall = _score(runs)
    categories: dict[str, list[CaseRun]] = {}
    for run in runs:
        categories.setdefault(run.category, []).append(run)

    return AccuracyReport(
        top1=overall.top1,
        top3=overall.top3,
        scored=len(runs),
        failed=sum(1 for run in runs if run.error is not None),
        by_category={name: _score(group) for name, group in sorted(categories.items())},
    )


@dataclass(frozen=True, slots=True)
class StabilityReport:
    """How much the same input moves the answer.

    ``top1_agreement`` is the share of repeats landing on the modal top candidate,
    counting every run in the denominator — a failed run has no top candidate, so
    it can never agree with anything, but it still counts as a run that did not
    agree; it does not vanish from the average the way it would if filtered out
    before scoring.
    Both ``top1_agreement`` and ``candidate_churn`` compare disorder ids through
    ``_normalise_id`` first, same as ``top1_hit``/``top3_hit`` — otherwise the exact
    formatting nondeterminism those exist to fold out (``insufficient_light`` vs
    ``insufficient-light``) would register as disagreement here instead.
    ``candidate_churn`` is mean pairwise Jaccard *distance* between candidate sets:
    0.0 is identical, 1.0 disjoint. ``question_drift`` is the same distance over the
    clarifying questions asked, after subtracting the deterministic mandatory ones
    (``_DETERMINISTIC_QUESTION_KEYS``) — those are asked on every run regardless of
    the model, so including them would dampen the score and hide how much the
    model's own question choice actually varies. Reported separately from
    ``candidate_churn`` because question variance and diagnostic instability are
    different failure modes (spec §3.4).
    """

    top1_agreement: float
    candidate_churn: float
    question_drift: float
    cases: int
    runs_per_case: float


def _jaccard_distance(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    return 1.0 - len(left & right) / len(union)


def _mean_pairwise_distance(sets: list[set[str]]) -> float:
    pairs = list(combinations(sets, 2))
    if not pairs:
        return 0.0
    return sum(_jaccard_distance(a, b) for a, b in pairs) / len(pairs)


def _modal_agreement(tops: list[str | None]) -> float:
    """Share of runs landing on the modal top candidate.

    ``tops`` holds one entry per run, ``None`` where the run had no candidates (a
    failed run, per ``eval/harness.py``). The denominator is always ``len(tops)`` —
    every run, failed or not. A failed run can never agree with anything, so it
    contributes to the denominator but never to the modal count; it must not
    disappear from both, which would let a failure vanish from the very number
    meant to measure instability (spec §5, applied here as it is in ``accuracy()``).
    """
    if not tops:
        return 0.0
    hits = [value for value in tops if value is not None]
    if not hits:
        return 0.0
    return max(hits.count(value) for value in set(hits)) / len(tops)


def stability(runs_by_case: dict[str, list[CaseRun]]) -> StabilityReport:
    """Aggregate variance across repeated runs of the same cases."""
    if not runs_by_case:
        return StabilityReport(0.0, 0.0, 0.0, cases=0, runs_per_case=0.0)

    agreements, churns, drifts = [], [], []
    for runs in runs_by_case.values():
        tops = [_normalise_id(r.candidates[0]) if r.candidates else None for r in runs]
        agreements.append(_modal_agreement(tops))
        churns.append(
            _mean_pairwise_distance([{_normalise_id(c) for c in r.candidates} for r in runs])
        )
        drifts.append(
            _mean_pairwise_distance(
                [set(r.questions_asked) - _DETERMINISTIC_QUESTION_KEYS for r in runs]
            )
        )

    total_runs = sum(len(runs) for runs in runs_by_case.values())
    return StabilityReport(
        top1_agreement=sum(agreements) / len(agreements),
        candidate_churn=sum(churns) / len(churns),
        question_drift=sum(drifts) / len(drifts),
        cases=len(runs_by_case),
        runs_per_case=total_runs / len(runs_by_case),
    )


def near_misses(runs: list[CaseRun], cases: dict[str, GoldenCase]) -> int:
    """Top-1 misses that landed on a disorder the case called confusable.

    Reported alongside top-1/top-3 rather than folded into them (see
    ``_accepted``): a miss onto ``also_acceptable`` is still a miss, but it is a
    different kind of miss from one onto something unrelated, and the public
    report says so as a separate number (spec §3.5, §6).
    """
    total = 0
    for run in runs:
        if top1_hit(run) or not run.candidates:
            continue
        also_acceptable = {_normalise_id(d) for d in cases[run.case_id].also_acceptable}
        if _normalise_id(run.candidates[0]) in also_acceptable:
            total += 1
    return total


def total_usage(runs: list[CaseRun]) -> UsageSnapshot | None:
    """Aggregate token usage and cost across every run passed in.

    The caller combines the main set and the stability repeats before calling
    this, so the total reflects the whole evaluation's spend, not just one part
    of it (Block A exists to make spend observable; the run that costs the most
    reported none until now).

    Mirrors ``UsageCollector.snapshot()``'s convention: ``None`` when no run
    recorded any usage at all, rather than a zeroed snapshot that would read as a
    free run. Cost is summed only from runs that reported one and is ``None`` if
    none did — never a fabricated ``$0.00`` (consistent with
    ``ui/components/cost_badge.py``).
    """
    usages = [run.usage for run in runs if run.usage is not None]
    if not usages:
        return None

    costs = [usage.cost_usd for usage in usages if usage.cost_usd is not None]
    return UsageSnapshot(
        prompt_tokens=sum(usage.prompt_tokens for usage in usages),
        completion_tokens=sum(usage.completion_tokens for usage in usages),
        cost_usd=round(sum(costs), 8) if costs else None,
    )
