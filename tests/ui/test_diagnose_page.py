"""Smoke tests for the diagnose page.

Deliberately shallow — the logic lives below the UI and is tested there. These prove
the page renders, accepts input, and shows errors as messages rather than tracebacks.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.ui

# AppTest.from_file resolves a relative path against the calling file's directory,
# not the working directory — so this must be absolute to run from anywhere.
_DIAGNOSE_PAGE = Path(__file__).resolve().parent.parent.parent / "ui" / "pages" / "diagnose.py"


@pytest.fixture
def app(monkeypatch, make_deps, pipeline_models, tmp_path):
    """The diagnose page with the real service swapped for a faked one."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
    from services.diagnosis_service import DiagnosisService

    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    service = DiagnosisService(
        deps, build_diagnosis_graph(deps, MemorySaver()), upload_dir=tmp_path
    )

    monkeypatch.setattr("ui.bootstrap.get_service", lambda: service)
    return AppTest.from_file(str(_DIAGNOSE_PAGE), default_timeout=30)


def test_page_renders_without_exception(app):
    app.run()
    assert not app.exception


def test_page_shows_its_title(app):
    app.run()
    assert any("Diagnose" in t.value for t in app.title)


def test_the_intake_form_is_present(app):
    app.run()
    assert app.text_input
    assert app.radio


def test_submitting_with_no_photos_shows_an_error_not_a_traceback(app):
    app.run()
    app.button[0].click().run()
    assert not app.exception
    assert app.error


# A real PNG magic-byte header. ``store_upload`` validates by magic bytes, not
# filename, so this is enough to pass the guard without needing a decodable image —
# the pipeline's models are scripted fakes and never actually look at the pixels.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _submit_intake(app) -> None:
    """Upload one photo and click through the intake form."""
    app.file_uploader[0].upload("leaf.png", _PNG_BYTES, "image/png")
    diagnose_button = next(b for b in app.button if b.label == "Diagnose")
    diagnose_button.click().run()


def test_questions_stage_renders_after_a_successful_start(app):
    """A valid upload advances past intake to the clarifying questions."""
    app.run()
    _submit_intake(app)

    assert not app.exception
    assert app.session_state["stage"] == "questions"
    # The question text from ``pipeline_models``'s scripted QuestionSet.
    assert any(t.label == "How much light?" for t in app.text_input)


def test_result_stage_renders_a_differential(app):
    """Completing the wizard renders the ranked candidates, not just a status."""
    app.run()
    _submit_intake(app)
    assert not app.exception

    answer = next(t for t in app.text_input if t.label == "How much light?")
    answer.set_value("A few hours of morning sun")
    submit_button = next(b for b in app.button if b.label == "Get my diagnosis")
    submit_button.click().run()

    assert not app.exception
    assert app.session_state["stage"] == "result"
    # The scripted Differential names "Overwatering" as the top candidate at 70%.
    headings = [s.value for s in app.subheader]
    assert any("Overwatering" in h and "70%" in h for h in headings)
    # Its distinguishing test is rendered too, not just the candidate name.
    assert any("Feel the soil" in i.value for i in app.info)
    # No candidate here is transmissible, so no contagion warning should appear.
    assert not app.warning


def test_a_raising_answer_call_shows_an_error_not_a_traceback(app, monkeypatch):
    """service.answer() can raise (e.g. the SQLite write failure persist re-raises).

    The photos have already been analysed by that point, so a bare traceback would
    both look broken and throw away a diagnosis the user already paid for. The page
    must catch it and show a message instead.
    """
    app.run()
    _submit_intake(app)
    assert not app.exception

    # The ``app`` fixture already replaced ``ui.bootstrap.get_service`` with a lambda
    # returning one fixed service instance — fetch that same instance and make its
    # ``answer`` raise, the way a real SQLite write failure re-raises out of persist.
    import ui.bootstrap as bootstrap_module

    def _explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(bootstrap_module.get_service(), "answer", _explode)

    answer = next(t for t in app.text_input if t.label == "How much light?")
    answer.set_value("A few hours of morning sun")
    submit_button = next(b for b in app.button if b.label == "Get my diagnosis")
    submit_button.click().run()

    assert not app.exception
    assert app.error
    assert app.session_state["stage"] == "questions"


def test_healthy_result_does_not_claim_no_treatment_plan(monkeypatch, make_deps, tmp_path):
    """A healthy plant is a first-class success outcome (PLAN §14), not a diagnosis
    that happens to be missing its roadmap. Rendering both messages together reads as
    a contradiction: "this plant looks healthy" immediately followed by "no treatment
    plan was produced for this diagnosis".
    """
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
    from agent.schemas import (
        Differential,
        ImageQuality,
        PlantCheck,
        Question,
        QuestionSet,
        Severity,
        SpeciesGuess,
        Symptom,
        SymptomPosition,
        SymptomSet,
    )
    from services.diagnosis_service import DiagnosisService
    from tests.fakes.chat_models import ScriptedStructuredModel

    gate = ScriptedStructuredModel(
        [
            PlantCheck(is_plant=True, what_it_is="a potted basil plant"),
            ImageQuality(usable=True, problem=None, guidance=None),
        ]
    )
    vision = ScriptedStructuredModel(
        [
            SpeciesGuess(common_name="Basil", scientific_name="Ocimum basilicum", confidence=0.9),
            SymptomSet(
                symptoms=[
                    Symptom(
                        description="No abnormality",
                        position=SymptomPosition.WHOLE_PLANT,
                        severity=Severity.MONITOR,
                    )
                ],
                soil_condition="moist",
                overall_vigor="good",
            ),
        ]
    )
    chat = ScriptedStructuredModel(
        [
            QuestionSet(
                questions=[Question(key="light_hours", text="How much light?", kind="text")]
            ),
            Differential(is_healthy=True, candidates=[], reasoning="No symptoms of concern."),
        ]
    )

    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    service = DiagnosisService(
        deps, build_diagnosis_graph(deps, MemorySaver()), upload_dir=tmp_path
    )
    monkeypatch.setattr("ui.bootstrap.get_service", lambda: service)

    app = AppTest.from_file(str(_DIAGNOSE_PAGE), default_timeout=30)
    app.run()
    _submit_intake(app)
    assert not app.exception

    answer = next(t for t in app.text_input if t.label == "How much light?")
    answer.set_value("Bright indirect light")
    submit_button = next(b for b in app.button if b.label == "Get my diagnosis")
    submit_button.click().run()

    assert not app.exception
    assert app.session_state["stage"] == "result"
    assert any("looks healthy" in s.value for s in app.success)
    assert not any("No treatment plan was produced" in i.value for i in app.info)


def test_thread_id_rotates_after_a_rejection(monkeypatch, make_deps, tmp_path):
    """A second attempt after a rejection must not resume the abandoned run's
    checkpoint (U7) — it should look exactly like a first attempt."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
    from agent.schemas import PlantCheck
    from services.diagnosis_service import DiagnosisService
    from tests.fakes.chat_models import ScriptedStructuredModel

    gate = ScriptedStructuredModel(
        [
            PlantCheck(is_plant=False, what_it_is="a photograph of a person"),
            PlantCheck(is_plant=False, what_it_is="a screenshot"),
        ]
    )
    deps = make_deps(gate_model=gate)
    service = DiagnosisService(
        deps, build_diagnosis_graph(deps, MemorySaver()), upload_dir=tmp_path
    )
    monkeypatch.setattr("ui.bootstrap.get_service", lambda: service)

    app = AppTest.from_file(str(_DIAGNOSE_PAGE), default_timeout=30)
    app.run()
    _submit_intake(app)
    first_thread = app.session_state["thread_id"]
    assert app.session_state["stage"] == "upload"

    _submit_intake(app)
    second_thread = app.session_state["thread_id"]

    assert first_thread != second_thread


def test_thread_id_rotates_after_a_retake(monkeypatch, make_deps, tmp_path):
    """The retake branch of the same rotation (U7). An unusable photo abandons the run
    just as a rejection does, so the retry must not resume its checkpoint either."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
    from agent.schemas import ImageQuality, PlantCheck
    from services.diagnosis_service import DiagnosisService
    from tests.fakes.chat_models import ScriptedStructuredModel

    gate = ScriptedStructuredModel(
        [
            PlantCheck(is_plant=True, what_it_is="a potted basil plant"),
            ImageQuality(usable=False, problem="blurry", guidance="Hold the camera steady."),
            PlantCheck(is_plant=True, what_it_is="a potted basil plant"),
            ImageQuality(usable=False, problem="too dark", guidance="Try daylight."),
        ]
    )
    deps = make_deps(gate_model=gate)
    service = DiagnosisService(
        deps, build_diagnosis_graph(deps, MemorySaver()), upload_dir=tmp_path
    )
    monkeypatch.setattr("ui.bootstrap.get_service", lambda: service)

    app = AppTest.from_file(str(_DIAGNOSE_PAGE), default_timeout=30)
    app.run()
    _submit_intake(app)
    first_thread = app.session_state["thread_id"]
    assert app.warning, "an unusable photo should ask for a retake"
    assert app.session_state["stage"] == "upload"

    _submit_intake(app)
    second_thread = app.session_state["thread_id"]

    assert first_thread != second_thread


def _finish_diagnosis(app) -> None:
    """Run the wizard from intake through to the result stage."""
    _submit_intake(app)
    answer = next(t for t in app.text_input if t.label == "How much light?")
    answer.set_value("A few hours of morning sun")
    next(b for b in app.button if b.label == "Get my diagnosis").click().run()


def _plant_service(monkeypatch, db, now):
    """A real PlantService on the test database, standing in for the cached one.

    Left unmocked, ``bootstrap.get_plant_service()`` returns an ``st.cache_resource``
    service holding a connection to the actual project database file — clicking
    "Save name" in a test would rename a row in production data.
    """
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
    return service


def test_the_result_offers_the_identified_species_as_a_name(app):
    """A plant left at the placeholder name is offered the identification to confirm
    — the scripted vision model names it Basil at 0.9 confidence."""
    app.run()
    _finish_diagnosis(app)

    assert not app.exception
    name_field = next(t for t in app.text_input if t.label == "Call it")
    assert name_field.value == "Basil"


def test_saving_the_confirmed_name_renames_the_plant(app, monkeypatch, db, now):
    service = _plant_service(monkeypatch, db, now)
    app.run()
    _finish_diagnosis(app)

    name_field = next(t for t in app.text_input if t.label == "Call it")
    name_field.set_value("Kitchen basil")
    next(b for b in app.button if b.label == "Save name").click().run()

    assert not app.exception
    assert [s.plant.name for s in service.list_plants()] == ["Kitchen basil"]
    assert any("Kitchen basil" in s.value for s in app.success)


def test_the_naming_prompt_is_gone_once_the_name_is_saved(app, monkeypatch, db, now):
    """Confirming is a one-time step. Leaving the form up would invite a second
    rename of a plant the owner has already named."""
    _plant_service(monkeypatch, db, now)
    app.run()
    _finish_diagnosis(app)
    next(b for b in app.button if b.label == "Save name").click().run()

    assert not any(t.label == "Call it" for t in app.text_input)


def test_intake_does_not_ask_for_a_name(app):
    """Identification is the agent's job. A name typed before it has happened is a
    guess made without the answer, so the question moved to after the diagnosis."""
    app.run()

    assert not any(t.label == "What do you call this plant?" for t in app.text_input)


def test_a_corrected_species_is_what_gets_suggested(app):
    """The owner's correction outranks the model's guess: if they say it is a
    rosemary, the name offered is Rosemary and not Basil."""
    app.run()
    _submit_intake(app)

    correction = next(
        t for t in app.text_input if t.label == "If that's wrong, tell me what it actually is"
    )
    correction.set_value("Rosemary")
    answer = next(t for t in app.text_input if t.label == "How much light?")
    answer.set_value("A few hours of morning sun")
    next(b for b in app.button if b.label == "Get my diagnosis").click().run()

    name_field = next(t for t in app.text_input if t.label == "Call it")
    assert name_field.value == "Rosemary"


def test_an_unidentified_plant_is_still_offered_a_name(
    monkeypatch, make_deps, tmp_path, pipeline_models
):
    """Nothing confident came back, so there is no suggestion to prefill — but the
    field still has to appear. Intake no longer asks for a name, so skipping the
    prompt here would strand the plant as "My plant" with nowhere to rename it.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
    from agent.schemas import (
        Severity,
        SpeciesGuess,
        Symptom,
        SymptomPosition,
        SymptomSet,
    )
    from services.diagnosis_service import DiagnosisService
    from tests.fakes.chat_models import ScriptedStructuredModel

    gate, _, chat = pipeline_models
    # Same script as the shared fixture's vision model, but hedging on the species:
    # 0.4 is below the confidence at which the page states a guess plainly.
    vision = ScriptedStructuredModel(
        [
            SpeciesGuess(common_name="Basil", scientific_name=None, confidence=0.4),
            SymptomSet(
                symptoms=[
                    Symptom(
                        description="Yellowing",
                        position=SymptomPosition.LOWER_LEAVES,
                        severity=Severity.ACT_THIS_WEEK,
                    )
                ],
                soil_condition="wet",
                overall_vigor="declining",
            ),
        ]
    )
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    service = DiagnosisService(
        deps, build_diagnosis_graph(deps, MemorySaver()), upload_dir=tmp_path
    )
    monkeypatch.setattr("ui.bootstrap.get_service", lambda: service)

    app = AppTest.from_file(str(_DIAGNOSE_PAGE), default_timeout=30)
    app.run()
    _finish_diagnosis(app)

    assert app.session_state["stage"] == "result"
    name_field = next(t for t in app.text_input if t.label == "Call it")
    assert name_field.value == "My plant", "no confident guess to prefill, so the placeholder"
