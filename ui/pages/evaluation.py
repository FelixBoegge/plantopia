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


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


left, middle, right = st.columns(3)
left.metric("Top-1 accuracy", _pct(accuracy["top1"]))
middle.metric("Top-3 accuracy", _pct(accuracy["top3"]))
right.metric("Faithfulness", _pct(ragas["faithfulness"]))

st.subheader("Retrieval quality")
st.dataframe(
    {
        "Metric": ["Context precision", "Context recall", "Answer relevancy"],
        "Score": [
            _pct(ragas["context_precision"]),
            _pct(ragas["context_recall"]),
            _pct(ragas["answer_relevancy"]),
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
