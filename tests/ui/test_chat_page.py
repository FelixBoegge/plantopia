"""Smoke tests for the Chat page."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.ui

_CHAT_PAGE = Path(__file__).resolve().parent.parent.parent / "ui" / "pages" / "chat.py"


@pytest.fixture
def app(monkeypatch, make_deps, db, now):
    from langchain_core.messages import AIMessage

    from data.repositories.messages import MessageRepository
    from data.repositories.plants import PlantRepository
    from services.chat_service import ChatService
    from tests.fakes.chat_models import ScriptedToolCallingModel

    plant_id = PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    model = ScriptedToolCallingModel(
        [AIMessage(content="Some yellowing on lower leaves is normal.")]
    )
    deps = make_deps(chat_model=model)
    service = ChatService(deps=deps, messages=MessageRepository(db), now=now)
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: service)

    at = AppTest.from_file(str(_CHAT_PAGE), default_timeout=30)
    at.session_state["chat_plant_id"] = plant_id
    return at


def test_page_renders_without_exception(app):
    app.run()
    assert not app.exception


def test_shows_a_prompt_when_no_plant_is_selected(monkeypatch, make_deps, db, now):
    from data.repositories.messages import MessageRepository
    from services.chat_service import ChatService

    deps = make_deps()
    service = ChatService(deps=deps, messages=MessageRepository(db), now=now)
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: service)

    at = AppTest.from_file(str(_CHAT_PAGE), default_timeout=30)
    at.run()
    assert not at.exception
    assert any("Choose a plant" in i.value for i in at.info)


def test_sending_a_message_shows_the_reply(app):
    app.run()
    app.chat_input[0].set_value("Is this normal?").run()
    assert not app.exception
    # ChatMessage is a container (Block), not a value-bearing element: the text
    # written inside it via st.write shows up as a nested markdown child.
    assert any("normal" in md.value.lower() for cm in app.chat_message for md in cm.markdown)
