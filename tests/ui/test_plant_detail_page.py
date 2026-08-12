"""Smoke tests for the Plant detail page."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.ui

_PLANT_DETAIL_PAGE = (
    Path(__file__).resolve().parent.parent.parent / "ui" / "pages" / "plant_detail.py"
)
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def app(monkeypatch, db, now, sample_plant, make_deps, tmp_path):
    """``sample_plant`` already has a prior diagnosis in ``db``, and ``deps`` shares
    that same ``db`` — so a re-check triggered through this page's ``diagnosis_service``
    genuinely reaches ``compare_progress`` with a real prior diagnosis to compare
    against. The chat model must therefore be scripted for the re-check shape
    (``ProgressVerdict`` then ``Roadmap``), not the first-time-diagnosis shape
    ``pipeline_models`` provides (``QuestionSet``/``Differential``/``Roadmap``) —
    using the wrong fixture here would hand `compare_progress` a `QuestionSet` where
    it expects a `ProgressVerdict`."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
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
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.feedback import FeedbackRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository
    from services.diagnosis_service import DiagnosisService
    from services.plant_service import PlantService
    from tests.fakes.chat_models import ScriptedStructuredModel

    plant_service = PlantService(
        plants=PlantRepository(db),
        observations=ObservationRepository(db),
        diagnoses=DiagnosisRepository(db),
        roadmap=RoadmapRepository(db),
        feedback=FeedbackRepository(db),
        now=now,
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
            ProgressVerdict(verdict="static", reasoning="No visible change yet."),
            Roadmap(
                steps=[
                    RoadmapStep(
                        ordinal=1,
                        action="Escalate to mechanical removal of affected roots.",
                        rationale="Cultural changes alone have not resolved it.",
                        success_signal="New growth is firm, not mushy.",
                        tier=IPMTier.MECHANICAL,
                        day_offset=0,
                    )
                ]
            ),
        ]
    )
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    diagnosis_service = DiagnosisService(
        deps, build_diagnosis_graph(deps, MemorySaver()), upload_dir=tmp_path
    )

    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: plant_service)
    monkeypatch.setattr("ui.bootstrap.get_service", lambda: diagnosis_service)

    at = AppTest.from_file(str(_PLANT_DETAIL_PAGE), default_timeout=30)
    at.session_state["selected_plant_id"] = sample_plant
    return at


def test_page_renders_without_exception(app):
    app.run()
    assert not app.exception


def test_shows_a_prompt_when_no_plant_is_selected(monkeypatch, db, now):
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.feedback import FeedbackRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository
    from services.plant_service import PlantService

    service = PlantService(
        plants=PlantRepository(db),
        observations=ObservationRepository(db),
        diagnoses=DiagnosisRepository(db),
        roadmap=RoadmapRepository(db),
        feedback=FeedbackRepository(db),
        now=now,
    )
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: service)

    at = AppTest.from_file(str(_PLANT_DETAIL_PAGE), default_timeout=30)
    at.run()
    assert not at.exception
    assert any("Choose a plant" in i.value for i in at.info)


def test_the_timeline_and_checklist_render(app):
    app.run()
    assert any("Overwatering" in m.value for m in app.markdown)
    assert len(app.checkbox) == 2  # sample_plant has two roadmap steps


def test_the_feedback_prompt_shows_because_a_step_is_done(app):
    app.run()
    assert any("Did this treatment help" in s.value for s in app.subheader)


def test_ticking_a_step_persists(app, db, sample_plant):
    app.run()
    pending_checkbox = next(c for c in app.checkbox if c.value is False)
    pending_checkbox.check().run()
    assert not app.exception

    from data.repositories.roadmap import RoadmapRepository

    steps = RoadmapRepository(db).list_for_plant(sample_plant)
    assert all(s.status == "done" for s in steps)


def test_recheck_button_starts_the_upload_flow(app):
    app.run()
    recheck_button = next(b for b in app.button if b.label == "Re-check this plant")
    recheck_button.click().run()
    assert not app.exception
    assert app.file_uploader


def test_completing_a_recheck_shows_the_verdict(app):
    """Renamed from ``..._shows_the_verdict_free_result``: the verdict was computed by
    ``compare_progress``, routed on, and then dropped by ``_final_result``, so the page
    genuinely had none to show. README advertises it, so it now renders."""
    app.run()
    next(b for b in app.button if b.label == "Re-check this plant").click().run()

    app.file_uploader[0].upload("leaf.png", _PNG_BYTES, "image/png")
    next(b for b in app.button if b.label == "Submit re-check").click().run()

    assert not app.exception
    # The scripted chat model answers "static" then a revised Roadmap, so this run
    # reaches revise_roadmap and persist without ever calling diagnose — proving the
    # page wires start_recheck end-to-end through the same routing Task 10 tests at
    # the graph level, this time via the actual page's buttons and file uploader.
    #
    # AppTest's session_state is a SafeSessionState, which (unlike the rest of this
    # test suite's bracket-access convention) has no .get() method — attribute lookup
    # falls through to __getattr__, which treats "get" as a missing session-state key
    # and raises KeyError. Use "in" plus bracket access instead.
    assert "recheck_result" in app.session_state
    assert app.session_state["recheck_result"] is not None

    verdict_lines = [m.value for m in app.markdown if "Verdict" in m.value]
    assert verdict_lines, "the re-check result block shows no verdict at all"
    assert any("static" in line for line in verdict_lines)
    # The verdict's own reasoning, not just the differential's, reaches the page.
    assert any("No visible change yet" in c.value for c in app.caption)


def test_submitting_recheck_without_photos_shows_a_friendly_error(app):
    """``start_recheck`` raises ``ValueError`` for an empty upload list. Before this
    fix, "Submit re-check" was clickable with no file chosen (it isn't inside an
    ``st.form``, so there's no built-in guard), and the page let that ``ValueError``
    surface as a raw, unhandled exception instead of a friendly error."""
    app.run()
    next(b for b in app.button if b.label == "Re-check this plant").click().run()

    next(b for b in app.button if b.label == "Submit re-check").click().run()

    assert not app.exception
    assert any("upload at least one photo" in e.value for e in app.error)


def test_recheck_result_does_not_leak_to_a_different_plant(app, db, now):
    """``recheck_stage``/``recheck_result`` are bare session-state keys, not scoped
    by plant. Completing a re-check on one plant and then navigating to another
    (still within the same Streamlit session) must not carry the first plant's
    stale re-check result over onto the second plant's page."""
    app.run()
    next(b for b in app.button if b.label == "Re-check this plant").click().run()
    app.file_uploader[0].upload("leaf.png", _PNG_BYTES, "image/png")
    next(b for b in app.button if b.label == "Submit re-check").click().run()
    assert app.session_state["recheck_result"] is not None

    from data.repositories.plants import PlantRepository

    other_plant_id = PlantRepository(db).create(
        name="Office pothos",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    app.session_state["selected_plant_id"] = other_plant_id
    app.run()

    assert not app.exception
    assert "recheck_result" not in app.session_state
    assert not any("Re-check complete" in s.value for s in app.success)
