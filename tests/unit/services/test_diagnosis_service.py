"""Tests for the diagnosis service — the only surface the UI calls."""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from agent.diagnosis_graph import build_diagnosis_graph
from agent.schemas import PlantCheck
from core.guards import UploadRejected
from services.diagnosis_service import DiagnosisService
from tests.fakes.chat_models import ScriptedStructuredModel

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


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
