"""Run the golden set and write the results file and report.

Costs real money and takes several minutes. Deliberately a CLI rather than a UI
button: a full run is minutes of model calls, and the report is more valuable as a
reviewable artefact in git than as something that exists only after someone waits
(spec §3.6).

    uv run python -m eval.run_eval
    uv run python -m eval.run_eval --stability-cases 8 --stability-runs 5

This module never imports ``ragas`` directly. ``ragas`` is only safely importable
after ``eval.ragas_metrics`` has installed its legacy-Vertex-AI compatibility shim
at module scope; importing ``ragas.llms``/``ragas.embeddings`` here, before that
shim has run, raises ``ModuleNotFoundError: langchain_community.chat_models.vertexai``.
``eval.ragas_metrics.judge_llm``/``judge_embeddings`` do the wrapping on the other
side of that shim, so this module only ever touches ``eval.ragas_metrics``.
"""

import argparse
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from agent.deps import Deps
from core.config import get_settings
from core.llm import build_embeddings, build_reasoning_model
from core.tracing import configure_tracing
from eval.cases import GoldenCase, load_cases
from eval.harness import CaseRun, run_case
from eval.metrics import accuracy, stability, top1_hit
from eval.ragas_metrics import evaluate_runs, judge_embeddings, judge_llm
from eval.report import render_report

logger = logging.getLogger(__name__)

GOLDEN_SET = Path("eval/golden_set")
RESULTS_DIR = Path("eval/results")
REPORT_PATH = Path("eval/REPORT.md")


def _as_dict(report) -> dict:
    return asdict(report)


def _case_row(run: CaseRun) -> dict:
    """Enough to audit one case without storing its full reasoning text."""
    return {
        "case_id": run.case_id,
        "ground_truth": run.ground_truth,
        "category": run.category,
        "candidates": run.candidates,
        "questions_asked": run.questions_asked,
        "error": run.error,
    }


def _near_misses(runs: list[CaseRun], cases: dict[str, GoldenCase]) -> int:
    """Top-1 misses that landed on a disorder the case called confusable."""
    total = 0
    for run in runs:
        if top1_hit(run) or not run.candidates:
            continue
        if run.candidates[0] in set(cases[run.case_id].also_acceptable):
            total += 1
    return total


def _run_one(case: GoldenCase, suffix: object) -> CaseRun:
    """One pass over one case, against a throwaway database.

    A fresh in-memory SQLite per case: ``persist`` writes a plant, an observation
    and a diagnosis on every run, and thirty cases times five repeats would
    otherwise pour ~180 junk plants into ``data/plantopia.db``. Chroma is built
    once at module import (``_retriever()``) because re-embedding the corpus per
    case would dominate both runtime and cost.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
    from data.db import apply_schema, connect
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository
    from eval.scripted import case_models
    from tools.care_profiles import lookup_plant_care_profile
    from tools.weather import get_local_weather
    from tools.web_search import web_search_plant_info

    settings = get_settings()
    conn = connect(":memory:")
    apply_schema(conn)

    gate, vision = case_models(case)
    deps = Deps(
        settings=settings,
        gate_model=gate,
        vision_model=vision,
        chat_model=build_reasoning_model(),
        retriever=_retriever(),
        plants=PlantRepository(conn),
        observations=ObservationRepository(conn),
        diagnoses=DiagnosisRepository(conn),
        roadmap=RoadmapRepository(conn),
        weather=get_local_weather,
        web_search=lambda query: web_search_plant_info(query, api_key=settings.tavily_api_key),
        care_profile=lookup_plant_care_profile,
        now=lambda: datetime.now(tz=UTC),
    )

    graph = build_diagnosis_graph(deps, MemorySaver())
    try:
        return run_case(case, deps=deps, graph=graph, thread_id=f"eval-{case.id}-{suffix}")
    finally:
        conn.close()


@lru_cache(maxsize=1)
def _retriever():
    """The real corpus retriever, built once for the whole run."""
    from knowledge.ingest import load_corpus
    from knowledge.retriever import ChromaRetriever, build_vectorstore

    settings = get_settings()
    vectorstore = build_vectorstore(
        chunks=load_corpus(settings.corpus_path),
        embeddings=build_embeddings(),
        persist_directory=settings.chroma_path,
    )
    # No image embedder: golden cases carry no photographs, so the cross-modal
    # path has nothing to embed even when multimodal_embeddings is on.
    return ChromaRetriever(vectorstore, None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Plantopia evaluation harness.")
    parser.add_argument("--stability-cases", type=int, default=8)
    parser.add_argument("--stability-runs", type=int, default=5)
    parser.add_argument("--golden-set", type=Path, default=GOLDEN_SET)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    configure_tracing(settings)

    cases = load_cases(args.golden_set)
    logger.info("loaded %d golden cases", len(cases))

    # Build one Deps and one graph per case: the gate and vision tiers are scripted
    # from the case itself (eval/scripted.py), so they cannot be shared.
    runs = [_run_one(case, index) for index, case in enumerate(cases)]

    subset = cases[: args.stability_cases]
    repeats: dict[str, list[CaseRun]] = {
        case.id: [
            _run_one(case, f"stability-{index}-{repeat}") for repeat in range(args.stability_runs)
        ]
        for index, case in enumerate(subset)
    }

    accuracy_report = accuracy(runs)
    stability_report = stability(repeats)
    ragas_result = evaluate_runs(runs, llm=judge_llm(), embeddings=judge_embeddings())

    results = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provenance": {
            "reasoning_model": settings.reasoning_model,
            "vision_model": "scripted",
            "embedding_model": settings.embedding_model,
            "temperature": settings.default_temperature,
            "corpus_documents": len(list(settings.corpus_path.glob("*.md"))),
            "golden_set_size": len(cases),
        },
        "accuracy": _as_dict(accuracy_report),
        "ragas": ragas_result.scores,
        # Non-NaN cells per metric out of cells submitted to Ragas, so a reader can
        # audit later whether a mean quietly came from fewer cases than it looks
        # like (spec §5) — see eval/ragas_metrics.py::RagasScores.
        "ragas_counts": ragas_result.counts,
        "stability": _as_dict(stability_report),
        "near_misses": _near_misses(runs, {case.id: case for case in cases}),
        "cases": [_case_row(run) for run in runs],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = results["generated_at"].replace(":", "-")
    (RESULTS_DIR / f"{stamp}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(render_report(results), encoding="utf-8")
    logger.info("wrote %s and %s", RESULTS_DIR / f"{stamp}.json", REPORT_PATH)


if __name__ == "__main__":
    main()
