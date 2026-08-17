"""UI tests for the learned-profile page.

The panel itself is covered in ``test_profile_panel.py``; these prove the page that
now carries it renders, reaches the real service, and can forget a fact.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.ui

# AppTest.from_file resolves a relative path against the calling file's directory,
# not the working directory — so this must be absolute to run from anywhere.
_PROFILE_PAGE = Path(__file__).resolve().parent.parent.parent / "ui" / "pages" / "profile.py"

_WHEN = datetime(2026, 8, 17, tzinfo=UTC)


@pytest.fixture
def profile(monkeypatch, db):
    """A real ProfileService on the test database, standing in for the cached one.

    Left unmocked, ``bootstrap.get_profile_service()`` opens a connection to the
    actual project database file, and "Forget" in a test would delete a fact the
    owner meant to keep.
    """
    from data.repositories.profile import ProfileRepository
    from services.profile_service import ProfileService
    from tests.fakes.chat_models import ScriptedStructuredModel

    service = ProfileService(
        repo=ProfileRepository(db), gate_model=ScriptedStructuredModel([]), now=lambda: _WHEN
    )
    monkeypatch.setattr("ui.bootstrap.get_profile_service", lambda: service)
    return service


def _remember(db, fact: str) -> None:
    from data.db import transaction
    from data.repositories.profile import ProfileRepository

    with transaction(db):
        ProfileRepository(db).upsert(fact=fact, source="stated", confidence=0.8, now=_WHEN)


def test_the_page_renders_with_nothing_learned(profile):
    app = AppTest.from_file(str(_PROFILE_PAGE), default_timeout=30).run()

    assert not app.exception
    assert any("learned" in t.value.lower() for t in app.title)


def test_a_stored_fact_is_shown(profile, db):
    _remember(db, "waters weekly")

    app = AppTest.from_file(str(_PROFILE_PAGE), default_timeout=30).run()

    assert not app.exception
    assert any("waters weekly" in m.value for m in app.markdown)


def test_forgetting_a_fact_removes_it(profile, db):
    """The delete control has to reach the real store, not just redraw the list —
    a page about what a system holds on someone is only worth having if its forget
    button forgets.
    """
    _remember(db, "waters weekly")
    app = AppTest.from_file(str(_PROFILE_PAGE), default_timeout=30).run()

    next(b for b in app.button if b.label == "Forget").click().run()

    assert not app.exception
    assert profile.all_facts() == []
