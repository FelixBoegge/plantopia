"""Evaluation results, rendered from the newest committed results file.

Renders only — it never runs the harness. A full evaluation is minutes of model
calls and real money, so it lives behind `uv run python -m eval.run_eval`, and this
page reads what that wrote (spec §4).
"""

import json
import os
from pathlib import Path

import streamlit as st

st.title("📊 Evaluation")


def _results_dir() -> Path:
    return Path(os.environ.get("PLANTOPIA_EVAL_RESULTS_DIR", "eval/results"))


def _latest_results() -> dict | None:
    files = sorted(_results_dir().glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


results = _latest_results()

if results is None:
    st.info(
        "No evaluation has been run yet. Run `uv run python -m eval.run_eval` to "
        "generate a report — it takes several minutes and makes real model calls."
    )
    st.stop()

provenance = results["provenance"]
st.caption(
    f"Generated {results['generated_at']} · reasoning model "
    f"`{provenance['reasoning_model']}` · temperature {provenance['temperature']} · "
    f"{provenance['corpus_documents']} corpus documents · "
    f"{provenance['golden_set_size']} golden cases"
)

accuracy = results["accuracy"]
ragas = results["ragas"]
# Absent entirely in results files written before this counts field existed — an
# empty dict falls through _ragas_metric's "no counts" branch below, so those
# older files keep rendering the bare percentage they always did.
ragas_counts = results.get("ragas_counts", {})


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


def _ragas_metric(value: float | None, counts: dict | None) -> str:
    """One Ragas metric's display string, disclosing partial scoring the same way
    ``eval/report.py``'s ``_ragas_cell`` does for the markdown report — a metric
    that failed on some cases must not read as a complete mean in the app just
    because it does in the terminal (spec §5).

    Falls back to the bare percentage when ``counts`` is missing or empty, which
    covers both a metric that scored everything and a results file that predates
    ``ragas_counts`` altogether.
    """
    pct = _pct(value)
    if not counts:
        return pct
    scored, total = counts.get("scored", 0), counts.get("total", 0)
    if total == 0 or scored == total:
        return pct
    return f"{pct} ({scored} of {total} scored)"


def _scored_note(counts: dict | None) -> str | None:
    """The partial-scoring disclosure as tooltip text, or ``None`` when complete.

    ``st.metric`` renders its value in a large type size that truncates, so the
    "(n of m scored)" suffix ``_ragas_metric`` appends — fine in a table cell —
    is cut off mid-phrase in a metric tile. The disclosure moves to ``help`` so
    the number stays legible without the caveat being dropped: a partially
    scored mean must never read as a complete one (spec §5).
    """
    if not counts:
        return None
    scored, total = counts.get("scored", 0), counts.get("total", 0)
    if total == 0 or scored == total:
        return None
    return (
        f"Averaged over {scored} of {total} cases — the remaining judge calls failed "
        "(M20). Treat this figure as partial, and do not compare it across runs, "
        "which score overlapping but different subsets."
    )


left, middle, right = st.columns(3)
left.metric("Top-1 accuracy", _pct(accuracy["top1"]))
middle.metric("Top-3 accuracy", _pct(accuracy["top3"]))
right.metric(
    "Faithfulness",
    _pct(ragas["faithfulness"]),
    help=_scored_note(ragas_counts.get("faithfulness")),
)

st.subheader("Retrieval quality")
st.dataframe(
    {
        "Metric": ["Context precision", "Context recall", "Answer relevancy"],
        "Score": [
            _ragas_metric(ragas["context_precision"], ragas_counts.get("context_precision")),
            _ragas_metric(ragas["context_recall"], ragas_counts.get("context_recall")),
            _ragas_metric(ragas["answer_relevancy"], ragas_counts.get("answer_relevancy")),
        ],
    },
    hide_index=True,
)

st.subheader("By category")
by_category = accuracy["by_category"]
st.bar_chart({name: scores["top1"] for name, scores in by_category.items()})

st.subheader("Stability")
stability = results["stability"]
st.caption(
    f"{stability['cases']} cases run {stability['runs_per_case']:.0f} times each on "
    "byte-identical input."
)
first, second, third = st.columns(3)
first.metric("Top-1 agreement", _pct(stability["top1_agreement"]))
second.metric("Candidate churn", _pct(stability["candidate_churn"]))
third.metric("Question drift", _pct(stability["question_drift"]))

st.subheader("What this does not measure")
st.markdown(
    "- **The vision layer.** Golden cases supply symptoms as text and are injected "
    "past `identify_plant` and `assess_symptoms`, so nothing here scores species "
    "identification or symptom extraction from a photograph.\n"
    "- **Chat.** Not exercised, and its token usage is not tracked at all (`M17`).\n"
    "- **Photograph quality.** Every case assumes a usable photo; the quality gate "
    "is scripted to pass."
)
