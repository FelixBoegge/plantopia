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
