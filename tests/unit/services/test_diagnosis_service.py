"""Tests for the diagnosis service — the only surface the UI calls."""

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from agent.diagnosis_graph import build_diagnosis_graph
from agent.schemas import PlantCheck
from core.guards import UploadRejected
from services.diagnosis_service import DiagnosisService, FinalResult, StartResult
from tests.fakes.chat_models import ScriptedStructuredModel

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _service(make_deps, pipeline_models, upload_dir: Path) -> DiagnosisService:
    """Build a service wired with the happy-path scripted models.

    Mirrors the ``service`` fixture's construction, but as a plain callable so a
    test can build several in one body.

    ``upload_dir`` is required rather than defaulted: it used to default to
    ``Path()`` — the *current working directory* — which was harmless only while
    no caller reached the upload path. The moment one called ``start()``,
    ``store_upload`` began writing real files into the repository root. Pass
    ``tmp_path``.
    """
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    graph = build_diagnosis_graph(deps, MemorySaver())
    return DiagnosisService(deps, graph, upload_dir=upload_dir)


@pytest.fixture
def service(make_deps, pipeline_models, tmp_path):
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    graph = build_diagnosis_graph(deps, MemorySaver())
    return DiagnosisService(deps, graph, upload_dir=tmp_path)


def test_start_returns_questions(service):
    result = service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t1",
    )
    assert result.status == "questions"
    assert {q.key for q in result.questions} >= {"watering", "drainage"}


def test_start_reports_the_identified_species(service):
    result = service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t1a",
    )
    assert result.species is not None
    assert result.species.common_name == "Basil"


def test_a_species_correction_is_written_into_state(service):
    service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t1b",
    )
    service.answer({"watering": "daily"}, thread_id="t1b", species_override="Thai basil")
    snapshot = service._graph.get_state({"configurable": {"thread_id": "t1b"}})
    assert snapshot.values["species"].common_name == "Thai basil"


def test_a_species_correction_is_treated_as_certain(service):
    service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t1c",
    )
    service.answer({"watering": "daily"}, thread_id="t1c", species_override="Thai basil")
    snapshot = service._graph.get_state({"configurable": {"thread_id": "t1c"}})
    assert snapshot.values["species"].confidence == 1.0


def test_no_override_leaves_the_species_alone(service):
    service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t1d",
    )
    service.answer({"watering": "daily"}, thread_id="t1d")
    snapshot = service._graph.get_state({"configurable": {"thread_id": "t1d"}})
    assert snapshot.values["species"].common_name == "Basil"


def test_a_blank_override_is_ignored(service):
    service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t1e",
    )
    service.answer({"watering": "daily"}, thread_id="t1e", species_override="   ")
    snapshot = service._graph.get_state({"configurable": {"thread_id": "t1e"}})
    assert snapshot.values["species"].common_name == "Basil"


def test_answer_completes_the_diagnosis(service):
    service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t2",
    )
    final = service.answer({"watering": "every other day"}, thread_id="t2")
    assert final.differential is not None
    assert final.roadmap is not None
    assert final.diagnosis_id is not None


def test_a_rejected_upload_returns_a_rejection(make_deps, tmp_path):
    gate = ScriptedStructuredModel(
        [PlantCheck(is_plant=False, what_it_is="a photograph of a person")]
    )
    deps = make_deps(gate_model=gate)
    service = DiagnosisService(
        deps, build_diagnosis_graph(deps, MemorySaver()), upload_dir=tmp_path
    )
    result = service.start(
        uploads=[PNG],
        plant_name="x",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t3",
    )
    assert result.status == "rejected"
    assert "person" in result.message


def test_an_invalid_file_raises_before_the_graph_runs(service):
    with pytest.raises(UploadRejected):
        service.start(
            uploads=[b"#!/bin/sh"],
            plant_name="x",
            location_kind="indoor",
            location_text=None,
            user_notes=None,
            thread_id="t4",
        )


def test_no_uploads_raises(service):
    with pytest.raises(ValueError, match="at least one"):
        service.start(
            uploads=[],
            plant_name="x",
            location_kind="indoor",
            location_text=None,
            user_notes=None,
            thread_id="t5",
        )


def test_too_many_uploads_raises(service):
    with pytest.raises(ValueError, match="at most"):
        service.start(
            uploads=[PNG] * 20,
            plant_name="x",
            location_kind="indoor",
            location_text=None,
            user_notes=None,
            thread_id="t6",
        )


def test_uploads_are_written_to_disk(service, tmp_path):
    service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t7",
    )
    assert list(tmp_path.glob("*.png"))


def test_answering_an_unknown_thread_raises(service):
    with pytest.raises(ValueError, match="thread"):
        service.answer({"watering": "daily"}, thread_id="never-started")


def test_the_final_result_exposes_the_tools_that_ran(service):
    service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t8",
    )
    final = service.answer({"watering": "daily"}, thread_id="t8")
    assert "search_plant_knowledge" in final.tools_used


@pytest.fixture
def recheck_service(make_deps, tmp_path):
    def _make(*, gate, vision, chat):
        from agent.diagnosis_graph import build_diagnosis_graph

        deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
        graph = build_diagnosis_graph(deps, MemorySaver())
        return DiagnosisService(deps, graph, upload_dir=tmp_path)

    return _make


def test_start_recheck_returns_a_final_result_on_success(
    recheck_service, sample_plant, sample_images
):
    from agent.schemas import (
        ImageQuality,
        IPMTier,
        PlantCheck,
        ProgressVerdict,
        Roadmap,
        RoadmapStep,
        Severity,
        Symptom,
        SymptomPosition,
        SymptomSet,
    )

    gate = ScriptedStructuredModel(
        [
            PlantCheck(is_plant=True, what_it_is="a basil plant"),
            ImageQuality(usable=True, problem=None, guidance=None),
        ]
    )
    vision = ScriptedStructuredModel(
        [
            SymptomSet(
                symptoms=[
                    Symptom(
                        description="Fewer yellow leaves",
                        position=SymptomPosition.LOWER_LEAVES,
                        severity=Severity.MONITOR,
                    )
                ],
                soil_condition="drier",
                overall_vigor="good",
            )
        ]
    )
    chat = ScriptedStructuredModel(
        [
            ProgressVerdict(verdict="improving", reasoning="Fewer symptoms."),
            Roadmap(
                steps=[
                    RoadmapStep(
                        ordinal=1,
                        action="Continue.",
                        rationale="Working.",
                        success_signal="No new symptoms.",
                        tier=IPMTier.CULTURAL,
                        day_offset=7,
                    )
                ]
            ),
        ]
    )
    service = recheck_service(gate=gate, vision=vision, chat=chat)

    result = service.start_recheck(
        plant_id=sample_plant,
        uploads=[PNG],
        user_notes=None,
        thread_id="rc1",
    )
    assert isinstance(result, FinalResult)
    assert result.differential is not None
    assert result.diagnosis_id is not None
    # The graph computes a ProgressVerdict and routes on it; the service used to drop
    # it on the floor, so the page could never show the verdict README advertises.
    assert result.verdict == "improving"
    assert result.verdict_reasoning == "Fewer symptoms."


def test_a_first_time_diagnosis_has_no_verdict(service):
    """``verdict`` is only meaningful against a prior diagnosis. A first-time run
    never visits ``compare_progress``, so the field must stay ``None`` rather than
    inventing a comparison that never happened."""
    service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t9",
    )
    final = service.answer({"watering": "daily"}, thread_id="t9")
    assert final.verdict is None
    assert final.verdict_reasoning is None


def test_start_recheck_reports_a_rejection_like_start_does(recheck_service, sample_plant):
    gate = ScriptedStructuredModel([PlantCheck(is_plant=False, what_it_is="a screenshot")])
    service = recheck_service(
        gate=gate, vision=ScriptedStructuredModel([]), chat=ScriptedStructuredModel([])
    )
    result = service.start_recheck(
        plant_id=sample_plant, uploads=[PNG], user_notes=None, thread_id="rc2"
    )
    assert isinstance(result, StartResult)
    assert result.status == "rejected"


def test_start_recheck_of_a_never_identified_plant_acquires_a_species(recheck_service, db, now):
    """``start_recheck`` used to fill ``species`` with an "Unknown" placeholder, which
    satisfied both ``identify_plant``'s idempotency guard and the router's skip — so a
    plant whose first diagnosis never identified it could never acquire a species."""
    from agent.schemas import (
        ImageQuality,
        IPMTier,
        PlantCheck,
        Roadmap,
        RoadmapStep,
        Severity,
        SpeciesGuess,
        Symptom,
        SymptomPosition,
        SymptomSet,
    )
    from data.repositories.plants import PlantRepository

    plant_id = PlantRepository(db).create(
        name="Mystery plant",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )

    gate = ScriptedStructuredModel(
        [
            PlantCheck(is_plant=True, what_it_is="some kind of herb"),
            ImageQuality(usable=True, problem=None, guidance=None),
        ]
    )
    vision = ScriptedStructuredModel(
        [
            SpeciesGuess(common_name="Sweet basil", scientific_name=None, confidence=0.8),
            SymptomSet(
                symptoms=[
                    Symptom(
                        description="Fewer yellow leaves",
                        position=SymptomPosition.LOWER_LEAVES,
                        severity=Severity.MONITOR,
                    )
                ],
                soil_condition="drier",
                overall_vigor="good",
            ),
        ]
    )
    # No prior diagnosis exists, so compare_progress returns new_problem and the run
    # rejoins the full chain: differential, then roadmap.
    chat = ScriptedStructuredModel(
        [
            _differential_for_recheck(),
            Roadmap(
                steps=[
                    RoadmapStep(
                        ordinal=1,
                        action="Move it somewhere brighter.",
                        rationale="Basil wants full sun.",
                        success_signal="New leaves are a darker green.",
                        tier=IPMTier.CULTURAL,
                        day_offset=0,
                    )
                ]
            ),
        ]
    )
    service = recheck_service(gate=gate, vision=vision, chat=chat)

    result = service.start_recheck(
        plant_id=plant_id, uploads=[PNG], user_notes=None, thread_id="rc-unidentified"
    )

    assert isinstance(result, FinalResult)
    assert vision.call_count == 2, "identify_plant was skipped, so no species was ever acquired"
    # It still took the re-check path afterwards, and with no prior diagnosis to compare
    # against the verdict is new_problem, which rejoins the full chain.
    assert result.verdict == "new_problem"
    assert result.differential is not None
    assert result.roadmap is not None
    assert result.diagnosis_id is not None


def _differential_for_recheck():
    from agent.schemas import Candidate, Differential, Severity

    return Differential(
        is_healthy=False,
        reasoning="Pale, stretched growth.",
        candidates=[
            Candidate(
                disorder_id="insufficient-light",
                name="Insufficient light",
                probability=0.7,
                supporting_evidence=["stretched stems"],
                contradicting_evidence=[],
                distinguishing_test="Compare growth after two weeks in a brighter spot.",
                severity=Severity.ACT_THIS_WEEK,
                transmissible=False,
            ),
            Candidate(
                disorder_id="overwatering",
                name="Overwatering",
                probability=0.3,
                supporting_evidence=["wet soil"],
                contradicting_evidence=[],
                distinguishing_test="Feel the soil three days after watering.",
                severity=Severity.MONITOR,
                transmissible=False,
            ),
        ],
    )


def test_start_recheck_raises_for_an_unknown_plant(recheck_service):
    service = recheck_service(
        gate=ScriptedStructuredModel([]),
        vision=ScriptedStructuredModel([]),
        chat=ScriptedStructuredModel([]),
    )
    with pytest.raises(ValueError, match="No plant"):
        service.start_recheck(plant_id=999_999, uploads=[PNG], user_notes=None, thread_id="rc3")


def test_one_collector_spans_start_and_answer(make_deps, pipeline_models, sample_images, tmp_path):
    """The vision calls happen in start(); the persist happens in answer(). One
    collector must see both, or cost undercounts by roughly half."""
    service = _service(make_deps, pipeline_models, tmp_path)

    first = service._run_config("thread-a")
    second = service._run_config("thread-a")

    assert first["configurable"]["usage_collector"] is second["configurable"]["usage_collector"]


def test_different_threads_get_different_collectors(make_deps, pipeline_models, tmp_path):
    service = _service(make_deps, pipeline_models, tmp_path)

    a = service._run_config("thread-a")["configurable"]["usage_collector"]
    b = service._run_config("thread-b")["configurable"]["usage_collector"]

    assert a is not b


def test_the_collector_is_also_a_callback(make_deps, pipeline_models, tmp_path):
    """Passed twice on purpose: as a callback to observe calls, and through
    configurable so persist can read it (spec §2.1)."""
    service = _service(make_deps, pipeline_models, tmp_path)

    config = service._run_config("thread-a")

    assert config["callbacks"] == [config["configurable"]["usage_collector"]]


def test_collectors_are_evicted_at_a_terminal_outcome(make_deps, pipeline_models, tmp_path):
    """Otherwise the dict grows for the life of the process."""
    service = _service(make_deps, pipeline_models, tmp_path)
    service._run_config("thread-a")

    service._release("thread-a")

    assert "thread-a" not in service._collectors


def test_releasing_an_unknown_thread_is_harmless(make_deps, pipeline_models, tmp_path):
    service = _service(make_deps, pipeline_models, tmp_path)

    service._release("never-seen")  # must not raise


def test_an_exception_out_of_invoke_releases_the_collector_in_start(
    make_deps, pipeline_models, tmp_path
):
    """A model call raising mid-graph must not leave that thread's collector behind
    forever — the same leak the ``RuntimeError`` "finished without interrupting"
    branch already guarded against, but for any exception, not just that one."""
    service = _service(make_deps, pipeline_models, tmp_path)
    service._graph.invoke = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        service.start(
            uploads=[PNG],
            plant_name="Basil",
            location_kind="indoor",
            location_text=None,
            user_notes=None,
            thread_id="t-boom",
        )

    assert "t-boom" not in service._collectors


def test_an_exception_out_of_invoke_releases_the_collector_in_answer(
    make_deps, pipeline_models, tmp_path
):
    service = _service(make_deps, pipeline_models, tmp_path)
    service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t-boom-2",
    )
    assert "t-boom-2" in service._collectors  # start() left the collector for answer()

    service._graph.invoke = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        service.answer({"watering": "daily"}, thread_id="t-boom-2")

    assert "t-boom-2" not in service._collectors


def test_an_exception_out_of_invoke_releases_the_collector_in_start_recheck(
    recheck_service, sample_plant
):
    service = recheck_service(
        gate=ScriptedStructuredModel([]),
        vision=ScriptedStructuredModel([]),
        chat=ScriptedStructuredModel([]),
    )
    service._graph.invoke = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        service.start_recheck(
            plant_id=sample_plant, uploads=[PNG], user_notes=None, thread_id="rc-boom"
        )

    assert "rc-boom" not in service._collectors


def test_a_pending_clarifying_question_session_still_keeps_its_collector(
    make_deps, pipeline_models, tmp_path
):
    """The one thread that legitimately survives ``start()`` without exception: it
    paused at the clarifying-question interrupt, and ``answer()`` needs the same
    collector to keep counting the gate/vision calls already made."""
    service = _service(make_deps, pipeline_models, tmp_path)

    result = service.start(
        uploads=[PNG],
        plant_name="Basil",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        thread_id="t-pending",
    )

    assert result.status == "questions"
    assert "t-pending" in service._collectors
