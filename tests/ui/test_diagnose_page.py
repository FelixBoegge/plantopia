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
