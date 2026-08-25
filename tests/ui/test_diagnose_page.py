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
    service = DiagnosisService(deps, build_diagnosis_graph(deps, MemorySaver()))

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
        Hypotheses,
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
            Hypotheses(doc_ids=["overwatering", "root-rot"], reasoning="scripted"),
            Differential(is_healthy=True, candidates=[], reasoning="No symptoms of concern."),
        ]
    )

    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    service = DiagnosisService(deps, build_diagnosis_graph(deps, MemorySaver()))
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
    service = DiagnosisService(deps, build_diagnosis_graph(deps, MemorySaver()))
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
    service = DiagnosisService(deps, build_diagnosis_graph(deps, MemorySaver()))
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


def _plant_service(owner, monkeypatch, db, now):
    """A real PlantService on the test database, standing in for the cached one.

    Left unmocked, ``bootstrap.get_plant_service()`` returns an ``st.cache_resource``
    service holding a connection to the actual project database file — finishing a
    diagnosis in a test would then rename a row in production data.
    """
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.feedback import FeedbackRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository
    from services.plant_service import PlantService

    service = PlantService(
        user_id=owner,
        plants=PlantRepository(db),
        observations=ObservationRepository(db),
        diagnoses=DiagnosisRepository(db),
        roadmap=RoadmapRepository(db),
        feedback=FeedbackRepository(db),
        now=now,
    )
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: service)
    return service


_NAME_FIELD = "What should I call this plant?"


def test_intake_does_not_ask_for_a_name(app):
    """Identification is the agent's job. A name typed before it has happened is a
    guess made without the answer, so the question moved past identification."""
    app.run()

    assert not any(t.label == "What do you call this plant?" for t in app.text_input)


def test_the_name_field_is_prefilled_with_the_identification(app):
    """Prefilled, not a placeholder hint: the agent has made its suggestion, and
    accepting it should cost nothing. The scripted vision model says Basil."""
    app.run()
    _submit_intake(app)

    assert next(t for t in app.text_input if t.label == _NAME_FIELD).value == "Basil"


def test_accepting_the_suggestion_names_the_plant(owner, app, monkeypatch, db, now):
    service = _plant_service(owner, monkeypatch, db, now)
    app.run()
    _finish_diagnosis(app)

    assert not app.exception
    assert [s.plant.name for s in service.list_plants()] == ["Basil"]


def test_a_name_typed_over_the_suggestion_is_the_one_kept(owner, app, monkeypatch, db, now):
    service = _plant_service(owner, monkeypatch, db, now)
    app.run()
    _submit_intake(app)

    next(t for t in app.text_input if t.label == _NAME_FIELD).set_value("Kitchen basil")
    next(t for t in app.text_input if t.label == "How much light?").set_value("Morning sun")
    next(b for b in app.button if b.label == "Get my diagnosis").click().run()

    assert not app.exception
    assert [s.plant.name for s in service.list_plants()] == ["Kitchen basil"]


def test_the_result_has_no_separate_naming_section(owner, app, monkeypatch, db, now):
    """Naming happens at the questions step now. A second prompt at the end would ask
    the owner to name a plant they have already named."""
    _plant_service(owner, monkeypatch, db, now)
    app.run()
    _finish_diagnosis(app)

    assert app.session_state["stage"] == "result"
    assert not any("Name this plant" in s.value for s in app.subheader)


def test_an_untouched_field_is_not_sent_as_a_species_correction(owner, app, monkeypatch, db, now):
    """``DiagnosisService.answer`` treats an override as certain: it rewrites the
    species at confidence 1.0 and drops the scientific name. Prefilling the field
    must not turn a hedged guess into a certainty just because the owner left it
    alone, so only text that differs from the guess counts as a correction.
    """
    _plant_service(owner, monkeypatch, db, now)
    app.run()
    _submit_intake(app)

    import ui.bootstrap as bootstrap_module

    seen = {}
    service = bootstrap_module.get_service()
    original = service.answer

    def _spy(*args, **kwargs):
        seen["species_override"] = kwargs.get("species_override")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "answer", _spy)

    next(t for t in app.text_input if t.label == "How much light?").set_value("Morning sun")
    next(b for b in app.button if b.label == "Get my diagnosis").click().run()

    assert seen["species_override"] is None


def test_a_changed_name_is_still_sent_as_a_species_correction(owner, app, monkeypatch, db, now):
    """The other half of the rule above: the owner knows their plant better than a
    photograph does, so a name they typed themselves still reaches the diagnosis."""
    _plant_service(owner, monkeypatch, db, now)
    app.run()
    _submit_intake(app)

    import ui.bootstrap as bootstrap_module

    seen = {}
    service = bootstrap_module.get_service()
    original = service.answer

    def _spy(*args, **kwargs):
        seen["species_override"] = kwargs.get("species_override")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "answer", _spy)

    next(t for t in app.text_input if t.label == _NAME_FIELD).set_value("Rosemary")
    next(t for t in app.text_input if t.label == "How much light?").set_value("Morning sun")
    next(b for b in app.button if b.label == "Get my diagnosis").click().run()

    assert seen["species_override"] == "Rosemary"


def test_arriving_after_a_finished_diagnosis_starts_a_fresh_one(owner, app, monkeypatch, db, now):
    """Coming back to a completed diagnosis begins a new one.

    ``app.py`` sets ``arrived_on_page`` on the first rerun after a move, which is the
    only signal a page has for "the user just got here" as opposed to "the user
    clicked something" — every rerun re-executes the whole script either way. Without
    the reset, a finished wizard was still sitting at its result on the way back from
    My Plants, and the route to a clean start was a button at the foot of a diagnosis
    the owner had already read.
    """
    _plant_service(owner, monkeypatch, db, now)
    app.run()
    _finish_diagnosis(app)
    assert app.session_state["stage"] == "result"
    finished_thread = app.session_state["thread_id"]

    app.session_state["arrived_on_page"] = True
    app.run()

    assert app.session_state["stage"] == "upload"
    assert "result" not in app.session_state
    assert app.session_state["thread_id"] != finished_thread, (
        "a new diagnosis must not resume the finished run's checkpoint"
    )


def test_returning_to_a_wizard_in_flight_resumes_it(owner, app):
    """Only a finished diagnosis is cleared. A run paused at its questions has already
    had its photos analysed and paid for, and clicking the Diagnose tab is how the
    owner comes back to it — restarting there would throw away work they were told
    was in progress.
    """
    app.run()
    _submit_intake(app)
    assert app.session_state["stage"] == "questions"
    running_thread = app.session_state["thread_id"]

    app.session_state["arrived_on_page"] = True
    app.run()

    assert app.session_state["stage"] == "questions"
    assert app.session_state["thread_id"] == running_thread
    assert any(t.label == "How much light?" for t in app.text_input)


def test_clicking_within_the_wizard_does_not_reset_it(app):
    """The reset keys off arrival, not off every rerun — otherwise submitting the
    intake form would wipe the very state that submission produced."""
    app.run()
    _submit_intake(app)

    assert app.session_state["stage"] == "questions"

    app.run()

    assert app.session_state["stage"] == "questions"
