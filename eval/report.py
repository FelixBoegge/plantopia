"""Render an evaluation results dict as committed markdown."""

from typing import Any

_NOT_MEASURED = "_not measured_"

# Context precision is scored over the passages similarity ranked, not everything the
# diagnosis read (``eval/ragas_metrics.py::evaluate_runs``). Said in the table itself
# because the basis changed: figures from runs before hypothesis-driven retrieval were
# computed over every context, so an unlabelled number here invites a comparison
# between two different denominators.
_PRECISION_BASIS = "(ranked passages only)"


def _pct(value: Any) -> str:
    if value is None:
        return _NOT_MEASURED
    return f"{float(value) * 100:.1f}%"


def _ragas_cell(value: Any, counts: dict[str, Any] | None) -> str:
    """Render one Ragas metric, disclosing incompleteness where it applies.

    A metric that scored every submitted case renders as a bare percentage — the
    common case should not be cluttered with a redundant note. One that scored
    fewer cells than were submitted says so right next to the number, including
    the case where it scored nothing at all: that still renders as "not measured"
    rather than 0.0%, but the count makes clear zero of how many were attempted
    (spec §5 — a report must state how many metrics failed, not quietly average
    over fewer cases). Missing counts (an older results file, or a caller that
    never populated them) fall back to the bare percentage.
    """
    pct = _pct(value)
    if not counts:
        return pct
    scored, total = counts.get("scored", 0), counts.get("total", 0)
    if total == 0 or scored == total:
        return pct
    return f"{pct} ({scored} of {total} scored)"


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _retry_note(retried: list[str] | None) -> str:
    """State whether any case needed a second attempt to produce its result.

    "0 failed" alone cannot distinguish a run where nothing went wrong from one where
    three cases failed and were rescued — and those are different reports about the
    same pipeline. A clean run says so explicitly rather than staying silent, because
    silence is what an older results file (which has no such field) also looks like.
    """
    if retried is None:
        return (
            "_This run predates retry tracking, so whether any case needed a second "
            "attempt is unknown._"
        )
    if not retried:
        return "No case needed a second attempt."
    names = ", ".join(f"`{case_id}`" for case_id in retried)
    return (
        f"**{len(retried)} {_plural(len(retried), 'case', 'cases')} failed on the first "
        f"attempt and succeeded on a retry:** {names}. The scores above are from the "
        "successful attempts, so a run that needed rescuing does not read as a clean one."
    )


def _usage_rows(provenance: dict[str, Any]) -> list[str]:
    """Provenance-table rows for total spend, or none at all if usage was never recorded.

    Renders tokens only when cost is ``None`` — never a fabricated ``$0.00`` —
    the same rule the per-diagnosis figures follow.
    """
    usage = provenance.get("total_token_usage")
    if not usage:
        return []
    rows = [
        f"| Total tokens | {usage['prompt_tokens']:,} in / "
        f"{usage['completion_tokens']:,} out ({usage['total_tokens']:,} total) |"
    ]
    cost = provenance.get("total_cost_usd")
    if cost is not None:
        rows.append(f"| Total cost | ${cost:.4f} |")
    return rows


def render_report(results: dict) -> str:
    """Render ``eval/REPORT.md`` from a results dict.

    Provenance is rendered first because a metrics table without the configuration
    that produced it cannot be reproduced, and this report is meant to be read
    months later (spec §3.6).
    """
    provenance = results["provenance"]
    accuracy = results["accuracy"]
    ragas = results["ragas"]
    ragas_counts = results.get("ragas_counts", {})
    stability = results["stability"]
    stability_case_ids = results.get("stability_case_ids", [])

    lines = [
        "# Evaluation report",
        "",
        f"Generated {results['generated_at']} by `uv run python -m eval.run_eval`.",
        "",
        "## Run provenance",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Reasoning model | `{provenance['reasoning_model']}` |",
        f"| Vision tier | `{provenance['vision_model']}` |",
        f"| Embedding model | `{provenance['embedding_model']}` |",
        f"| Temperature | {provenance['temperature']} |",
        f"| Corpus documents | {provenance['corpus_documents']} |",
        f"| Golden-set size | {provenance['golden_set_size']} |",
        *(
            [f"| Profile | `{provenance['profile']}` |"]
            if provenance.get("profile") is not None
            else []
        ),
        *_usage_rows(provenance),
        "",
        "## Headline metrics",
        "",
        "| Metric | Score |",
        "|---|---|",
        f"| Top-1 diagnostic accuracy | {_pct(accuracy['top1'])} |",
        f"| Top-3 diagnostic accuracy | {_pct(accuracy['top3'])} |",
        f"| Context precision {_PRECISION_BASIS} | "
        f"{_ragas_cell(ragas['context_precision'], ragas_counts.get('context_precision'))} |",
        f"| Context recall | "
        f"{_ragas_cell(ragas['context_recall'], ragas_counts.get('context_recall'))} |",
        f"| Faithfulness | "
        f"{_ragas_cell(ragas['faithfulness'], ragas_counts.get('faithfulness'))} |",
        f"| Answer relevancy | "
        f"{_ragas_cell(ragas['answer_relevancy'], ragas_counts.get('answer_relevancy'))} |",
        "",
        f"{accuracy['scored']} cases scored, of which **{accuracy['failed']} failed** "
        "and are counted in the denominator rather than dropped. "
        f"{results.get('near_misses', 0)} top-1 "
        f"{_plural(results.get('near_misses', 0), 'miss', 'misses')} landed on a disorder "
        "the case listed as a confusable neighbour.",
        "",
        _retry_note(results.get("retried_cases")),
        "",
        "## By category",
        "",
        "| Category | Cases | Top-1 | Top-3 |",
        "|---|---|---|---|",
    ]

    for name, scores in accuracy["by_category"].items():
        lines.append(
            f"| {name} | {scores['scored']} | {_pct(scores['top1'])} | {_pct(scores['top3'])} |"
        )

    lines += [
        "",
        "## Stability",
        "",
        f"{stability['cases']} cases run {stability['runs_per_case']:.0f} times each, on "
        "byte-identical input"
        + (
            f": {', '.join(f'`{case_id}`' for case_id in stability_case_ids)}."
            if stability_case_ids
            else "."
        ),
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Top-1 agreement | {_pct(stability['top1_agreement'])} |",
        f"| Candidate-set churn | {_pct(stability['candidate_churn'])} |",
        f"| Clarifying-question drift | {_pct(stability['question_drift'])} |",
        "",
        "Churn is mean pairwise Jaccard distance between candidate sets: 0% identical, "
        "100% disjoint. Question drift is the same measure over the clarifying questions "
        "asked, reported separately because those are model-generated — without it, "
        "question variance would read as diagnostic instability.",
        "",
        "Top-1 agreement and candidate-set churn normalise disorder-id formatting "
        "(`insufficient_light` vs `insufficient-light`) before comparing; figures from "
        "runs recorded before this normalisation was added to `stability()` were "
        "computed without it and may overstate disagreement slightly.",
        "",
        "## What this does not measure",
        "",
        "**The vision layer.** Golden cases supply symptoms as text and are injected past "
        "`identify_plant` and `assess_symptoms`, so nothing here says anything about "
        "species identification or symptom extraction from a photograph. Every metric "
        "above scores retrieval and reasoning only.",
        "",
        "**Chat.** The chat agent is not exercised, and its token usage is not tracked "
        "at all (`M17`).",
        "",
        "**Real-world photograph quality.** Every case assumes a usable photo; the "
        "quality gate is scripted to pass.",
        "",
    ]
    return "\n".join(lines)
