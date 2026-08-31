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
from eval.metrics import accuracy, near_misses, stability, total_usage
from eval.profiles import load_profile
from eval.ragas_metrics import evaluate_runs, judge_embeddings, judge_llm
from eval.report import render_report

logger = logging.getLogger(__name__)

GOLDEN_SET = Path("eval/golden_set")
# Read from settings so the API and the harness cannot end up reading and writing
# different directories.
RESULTS_DIR = get_settings().eval_results_path
REPORT_PATH = Path("eval/REPORT.md")
PROFILES_DIR = Path("eval/profiles")


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


def _run_one(case: GoldenCase, suffix: object, profile_block: str) -> CaseRun:
    """One pass over one case, against a throwaway database.

    A fresh in-memory SQLite per case: ``persist`` writes a plant, an observation
    and a diagnosis on every run, and thirty cases times five repeats would
    otherwise pour ~180 junk plants into ``data/plantopia.db``. Chroma is built
    once at module import (``_retriever()``) because re-embedding the corpus per
    case would dominate both runtime and cost.

    ``profile_block`` is the same rendered block for every case in a run — a
    profile describes the owner, not any one case (spec §4.3) — bound into a
    callable because ``Deps.profile_facts`` is read per run.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
    from agent.threads import diagnosis_thread
    from agent.wiring import harness_owner_id, open_session
    from core.blobs import PostgresBlobStore
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository
    from eval.scripted import case_models
    from tools.care_profiles import lookup_plant_care_profile
    from tools.weather import get_local_weather
    from tools.web_search import web_search_plant_info

    settings = get_settings()
    # The real database, not a throwaway one. A harness run writes plants and diagnoses
    # like any other run; keeping them is what lets a surprising score be investigated
    # afterwards rather than only re-run.
    session = open_session(settings)
    user_id = harness_owner_id(session)

    gate, vision = case_models(case)
    deps = Deps(
        settings=settings,
        user_id=user_id,
        gate_model=gate,
        vision_model=vision,
        chat_model=build_reasoning_model(),
        retriever=_retriever(),
        blobs=PostgresBlobStore(session),
        plants=PlantRepository(session),
        observations=ObservationRepository(session),
        diagnoses=DiagnosisRepository(session),
        roadmap=RoadmapRepository(session),
        # Wrapped rather than passed bare: `position` is keyword-only on the function and
        # the port passes four positional arguments.
        weather=lambda location, days, as_of=None, position=None: get_local_weather(
            location, days, as_of=as_of, position=position
        ),
        web_search=lambda query: web_search_plant_info(query, api_key=settings.tavily_api_key),
        # No second identification, deliberately. A golden case supplies its symptoms as
        # text and is injected past identification entirely, so asking a specialist
        # classifier what the photograph shows would spend a daily allowance on a question
        # nothing here scores — and would put a network call, and its failures, inside a
        # measurement that is supposed to vary only with the model.
        identify_species=lambda _photographs: [],
        # No place names either. A golden case carries no photograph with a position, so
        # this would be a network call answering a question nothing here asks.
        place_name=lambda _latitude, _longitude: None,
        care_profile=lookup_plant_care_profile,
        profile_facts=lambda: profile_block,
        now=lambda: datetime.now(tz=UTC),
    )

    graph = build_diagnosis_graph(deps, MemorySaver())
    # MemorySaver, not the Postgres one: a harness run has no interrupt to survive — the
    # answers are scripted — and a checkpoint per case would be litter with no reader.
    thread_id = diagnosis_thread(user_id)
    try:
        return run_case(case, deps=deps, graph=graph, thread_id=thread_id)
    finally:
        session.close()


@lru_cache(maxsize=1)
def _corpus():
    """The parsed corpus, loaded once for the whole run.

    Shared by ``_retriever`` (which embeds it) and ``main`` (which passes it to
    ``evaluate_runs`` to build Ragas' ``reference`` field), so it is parsed from
    disk exactly once rather than once per consumer.
    """
    from knowledge.ingest import load_corpus

    return load_corpus(get_settings().corpus_path)


@lru_cache(maxsize=1)
def _retriever():
    """The real corpus retriever, built once for the whole run."""
    from knowledge.retriever import ChromaRetriever, build_vectorstore

    settings = get_settings()
    vectorstore = build_vectorstore(
        chunks=_corpus(),
        embeddings=build_embeddings(),
        persist_directory=settings.chroma_path,
    )
    # No image embedder: golden cases carry no photographs, so the cross-modal
    # path has nothing to embed even when multimodal_embeddings is on.
    return ChromaRetriever(vectorstore, None)


def _run_main_set(cases: list[GoldenCase], profile_block: str) -> tuple[list[CaseRun], list[str]]:
    """Run every case once, giving a failed case one second attempt.

    A case can fail for reasons that have nothing to do with the diagnosis — a dropped
    connection, a structured-output parse that came back malformed once. Those are
    independent between attempts, so a single retry usually lands, and a run that
    spends an hour and a dollar should not report a case as unanswerable because one
    HTTP request died.

    The retry gets a fresh thread id rather than resuming: the first attempt's
    checkpoint may hold the state that failed, and resuming into it would reproduce the
    failure rather than escape it.

    Which cases needed two attempts is returned, not swallowed. A retry that quietly
    rescues a case would hide exactly the flakiness worth knowing about — three cases
    needing a second attempt is a different report from none, even when both end at 28
    of 28, so the ids go into the results file (spec §5's rule that a failure must stay
    visible, applied to a failure that was recovered).
    """
    runs: list[CaseRun] = []
    retried: list[str] = []

    for index, case in enumerate(cases):
        run = _run_one(case, index, profile_block)
        if run.error is not None:
            logger.warning("case %s failed (%s) — retrying once", case.id, run.error)
            retried.append(case.id)
            run = _run_one(case, f"retry-{index}", profile_block)
            if run.error is not None:
                logger.error("case %s failed twice: %s", case.id, run.error)
        runs.append(run)

    return runs, retried


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Plantopia evaluation harness.")
    parser.add_argument("--stability-cases", type=int, default=8)
    parser.add_argument("--stability-runs", type=int, default=5)
    parser.add_argument("--golden-set", type=Path, default=GOLDEN_SET)
    parser.add_argument(
        "--profile",
        default="empty",
        help="Name of a fixture under eval/profiles/ to inject as a run-level prior "
        "(spec §4.3). Defaults to 'empty', which renders as no block at all.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    configure_tracing(settings)

    cases = load_cases(args.golden_set)
    logger.info("loaded %d golden cases", len(cases))

    # One block for the whole run: a profile describes the owner, not any one
    # case, so every case and every stability repeat shares it (spec §4.3).
    profile_block = load_profile(args.profile, PROFILES_DIR)

    # Build one Deps and one graph per case: the gate and vision tiers are scripted
    # from the case itself (eval/scripted.py), so they cannot be shared.
    runs, retried = _run_main_set(cases, profile_block)

    subset = cases[: args.stability_cases]
    stability_case_ids = [case.id for case in subset]
    repeats: dict[str, list[CaseRun]] = {
        case.id: [
            _run_one(case, f"stability-{index}-{repeat}", profile_block)
            for repeat in range(args.stability_runs)
        ]
        for index, case in enumerate(subset)
    }

    all_runs = runs + [run for case_runs in repeats.values() for run in case_runs]
    usage_report = total_usage(all_runs)

    accuracy_report = accuracy(runs)
    stability_report = stability(repeats)
    ragas_result = evaluate_runs(
        runs, corpus=_corpus(), llm=judge_llm(), embeddings=judge_embeddings()
    )

    results = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provenance": {
            "reasoning_model": settings.reasoning_model,
            "vision_model": "scripted",
            "embedding_model": settings.embedding_model,
            "temperature": settings.default_temperature,
            "corpus_documents": len(list(settings.corpus_path.glob("*.md"))),
            "golden_set_size": len(cases),
            "profile": args.profile,
            # Sum of every model call in the run — the main set plus the stability
            # repeats — so the most expensive thing in the project finally reports
            # its own spend. ``None`` when no run reported cost, never a fabricated
            # $0.00 (consistent with ui/components/cost_badge.py).
            "total_token_usage": usage_report.as_token_usage() if usage_report else None,
            "total_cost_usd": usage_report.cost_usd if usage_report else None,
        },
        "accuracy": _as_dict(accuracy_report),
        "ragas": ragas_result.scores,
        # Non-NaN cells per metric out of cells submitted to Ragas, so a reader can
        # audit later whether a mean quietly came from fewer cases than it looks
        # like (spec §5) — see eval/ragas_metrics.py::RagasScores.
        "ragas_counts": ragas_result.counts,
        "stability": _as_dict(stability_report),
        # Which cases the stability subset actually ran, not just how many — the
        # ids are whichever sort first among the golden set, so naming them lets a
        # reader see which categories the repeated cases did (and did not) cover.
        "stability_case_ids": stability_case_ids,
        # Cases that failed once and were given a second attempt. Empty is the good
        # answer; a non-empty list means the run was flakier than "0 failed" suggests.
        "retried_cases": retried,
        "near_misses": near_misses(runs, {case.id: case for case in cases}),
        "cases": [_case_row(run) for run in runs],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = results["generated_at"].replace(":", "-")
    (RESULTS_DIR / f"{stamp}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(render_report(results), encoding="utf-8")
    logger.info("wrote %s and %s", RESULTS_DIR / f"{stamp}.json", REPORT_PATH)


if __name__ == "__main__":
    main()
