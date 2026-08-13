"""Render an evaluation results dict as committed markdown."""

from typing import Any

_NOT_MEASURED = "_not measured_"


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
        "",
        "## Headline metrics",
        "",
        "| Metric | Score |",
        "|---|---|",
        f"| Top-1 diagnostic accuracy | {_pct(accuracy['top1'])} |",
        f"| Top-3 diagnostic accuracy | {_pct(accuracy['top3'])} |",
        f"| Context precision | "
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
        f"{results.get('near_misses', 0)} top-1 misses landed on a disorder the case "
        "listed as a confusable neighbour.",
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
        "byte-identical input.",
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
