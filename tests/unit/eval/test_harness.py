"""Unit tests for the evaluation harness, using scripted models throughout."""

from agent.nodes.context import ALWAYS_ASK
from eval.harness import CaseRun, run_case


def _build_graph(deps):
    """The real graph with an in-memory checkpointer, as tests/graph/ builds it."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph

    return build_diagnosis_graph(deps, MemorySaver())


def test_a_completed_run_reports_ranked_candidates(make_deps, pipeline_models, golden_case):
    """The reasoning tier stays scripted here so this test needs no network."""
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    graph = _build_graph(deps)

    run = run_case(golden_case, deps=deps, graph=graph, thread_id="eval-1")

    assert run.candidates == ["overwatering", "root-rot"]
    assert run.error is None
    assert run.reasoning


def test_the_questions_asked_are_recorded(make_deps, pipeline_models, golden_case):
    """The complete set is recorded, mandatory questions included: this list is
    written verbatim into a committed, human-auditable results JSON, and filtering
    the mandatory keys out at capture time would permanently lose the fact that the
    owner was asked (and answered) watering and drainage. Subtracting them so only
    the model-chosen ``light_hours`` counts as drift is the drift metric's job, not
    the harness's (spec §3.4)."""
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)

    run = run_case(golden_case, deps=deps, graph=_build_graph(deps), thread_id="eval-2")

    assert run.questions_asked == [*(q.key for q in ALWAYS_ASK), "light_hours"]


def test_retrieved_passages_become_contexts(make_deps, pipeline_models, golden_case):
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)

    run = run_case(golden_case, deps=deps, graph=_build_graph(deps), thread_id="eval-3")

    assert all(isinstance(context, str) for context in run.contexts)


def test_a_failing_run_is_recorded_not_raised(make_deps, golden_case):
    """One bad case must not abort a 30-case run (spec §5)."""
    from tests.fakes.chat_models import FailingChatModel

    deps = make_deps(chat_model=FailingChatModel(RuntimeError("boom")))

    run = run_case(golden_case, deps=deps, graph=_build_graph(deps), thread_id="eval-4")

    assert isinstance(run, CaseRun)
    assert run.error is not None
    assert run.candidates == []


def test_the_case_metadata_is_carried_through(make_deps, pipeline_models, golden_case):
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)

    run = run_case(golden_case, deps=deps, graph=_build_graph(deps), thread_id="eval-5")

    assert run.case_id == golden_case.id
    assert run.ground_truth == "overwatering"
    assert run.category == "watering"
