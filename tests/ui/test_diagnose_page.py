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
