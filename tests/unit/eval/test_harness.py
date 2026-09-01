"""Unit tests for the evaluation harness, using scripted models throughout."""

from agent.nodes.context import ALWAYS_ASK, CAPTURE_KEY, LOCATION_KEY
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

    # `location` is among them now: it is asked on every run rather than only when an
    # outdoor plant had no location, because nobody is asked before the run starts any
    # more. Whether it is *required* is what varies, and that is not this list.
    assert run.questions_asked == [
        LOCATION_KEY,
        CAPTURE_KEY,
        *(q.key for q in ALWAYS_ASK),
        "light_hours",
    ]


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


def test_the_situation_carries_the_cases_symptoms_and_answers(
    make_deps, pipeline_models, golden_case
):
    """``situation`` is what feeds Ragas' ``user_input`` — it must carry the real
    case content (symptom descriptions plus the answers given), not a placeholder
    identical across every case (the defect this replaces)."""
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)

    run = run_case(golden_case, deps=deps, graph=_build_graph(deps), thread_id="eval-6")

    assert "yellowing lower leaves" in run.situation
    assert "four hours indirect" in run.situation


def test_two_different_cases_produce_different_situations(golden_case):
    """The defect this replaces: every case fed Ragas an identical sentence. Two
    cases with different symptoms and answers must now produce different
    ``situation`` values. Exercised directly against ``_situation`` — the piece
    that actually builds the string — rather than through a full graph run,
    which would need two independent scripted-model queues."""
    from eval.cases import GoldenCase
    from eval.harness import _situation

    other_case = GoldenCase.model_validate(
        {
            "id": "crispy-leaf-tips-test",
            "category": "watering",
            "plant": {"name": "Windowsill fern", "species": "Fern"},
            "species_confidence": 0.9,
            "symptoms": {
                "overall_vigor": "declining",
                "soil_condition": "bone dry",
                "symptoms": [
                    {
                        "description": "crisp brown edges on mature fronds",
                        "position": "leaf_margin",
                        "severity": "act_this_week",
                    }
                ],
            },
            "answers": {"light_hours": "six hours direct"},
            "ground_truth": "underwatering",
            "also_acceptable": [],
        }
    )

    situation_golden = _situation(golden_case, {"light_hours": "four hours indirect"})
    situation_other = _situation(other_case, {"light_hours": "six hours direct"})

    assert situation_golden != situation_other
    assert "yellowing lower leaves" in situation_golden
    assert "crisp brown edges on mature fronds" in situation_other


def test_situation_with_no_answers_still_states_the_symptoms():
    """A case whose interrupt path was never taken (no questions asked) must still
    produce a usable, non-empty situation from the symptoms alone."""
    from eval.cases import GoldenCase
    from eval.harness import _situation

    case = GoldenCase.model_validate(
        {
            "id": "no-answers-test",
            "category": "watering",
            "plant": {"name": "Test plant"},
            "symptoms": {
                "overall_vigor": "declining",
                "symptoms": [
                    {
                        "description": "wilting despite moist soil",
                        "position": "whole_leaf",
                        "severity": "monitor",
                    }
                ],
            },
            "ground_truth": "overwatering",
        }
    )

    situation = _situation(case, {})

    assert "wilting despite moist soil" in situation
    assert "Additional details" not in situation


def _case_with(**overrides):
    """A golden case, varied only where a test cares."""
    from eval.cases import GoldenCase

    base = {
        "id": "test-case",
        "category": "watering",
        "plant": {"name": "Kitchen basil", "species": "Basil"},
        "species_confidence": 0.9,
        "symptoms": {
            "overall_vigor": "declining",
            "soil_condition": "wet",
            "symptoms": [
                {
                    "description": "yellowing lower leaves",
                    "position": "lower_leaves",
                    "severity": "act_this_week",
                }
            ],
        },
        "answers": {},
        "ground_truth": "overwatering",
    }
    return GoldenCase.model_validate({**base, **overrides})


class TestAnsweringWhatWasAlreadyFilledIn:
    """The harness answers the way a person does: it leaves a filled field alone.

    Four outdoor golden cases carry `location_text: "Berlin"`, which now reaches the run as
    the location question's prefill rather than as state the enrich node reads directly.
    Answering those with the case's fallback would geocode "not observed" and lose the
    weather for the four cases where weather *is* the diagnosis.
    """

    def test_a_prefilled_answer_is_kept(self):
        from agent.schemas import Question
        from eval.harness import _answers_for

        case = _case_with(answers={})
        asked = [Question(key="location", text="Where is it?", kind="text", prefill="Berlin")]

        assert _answers_for(case, asked)["location"] == "Berlin"

    def test_the_case_still_wins_over_a_prefill(self):
        """A golden case that states an answer is stating what this case is about."""
        from agent.schemas import Question
        from eval.harness import _answers_for

        case = _case_with(answers={"location": "Reykjavik"})
        asked = [Question(key="location", text="Where is it?", kind="text", prefill="Berlin")]

        assert _answers_for(case, asked)["location"] == "Reykjavik"

    def test_an_unfilled_question_still_falls_back(self):
        from agent.schemas import Question
        from eval.harness import _answers_for

        case = _case_with(answers={})
        asked = [Question(key="treatments_tried", text="What have you tried?", kind="text")]

        assert _answers_for(case, asked)["treatments_tried"] == case.default_answer
