"""Smoke tests for the Chat page."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.ui

_CHAT_PAGE = Path(__file__).resolve().parent.parent.parent / "ui" / "pages" / "chat.py"


def _plant_service(db, now):
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.feedback import FeedbackRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository
    from services.plant_service import PlantService

    return PlantService(
        plants=PlantRepository(db),
        observations=ObservationRepository(db),
        diagnoses=DiagnosisRepository(db),
        roadmap=RoadmapRepository(db),
        feedback=FeedbackRepository(db),
        now=now,
    )


def _create_plant(db, now, name: str) -> int:
    from data.repositories.plants import PlantRepository

    return PlantRepository(db).create(
        name=name,
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )


@pytest.fixture
def app(monkeypatch, make_deps, db, now):
    from langchain_core.messages import AIMessage
    from langgraph.checkpoint.memory import MemorySaver

    from data.repositories.messages import MessageRepository
    from services.chat_service import ChatService
    from tests.fakes.chat_models import ScriptedToolCallingModel

    plant_id = _create_plant(db, now, "Basil")
    model = ScriptedToolCallingModel(
        [AIMessage(content="Some yellowing on lower leaves is normal.")]
    )
    deps = make_deps(chat_model=model)
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: service)
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: _plant_service(db, now))

    at = AppTest.from_file(str(_CHAT_PAGE), default_timeout=30)
    at.session_state["selected_plant_id"] = plant_id
    return at


def test_page_renders_without_exception(app):
    app.run()
    assert not app.exception


def test_shows_a_prompt_when_no_plant_is_selected(monkeypatch, make_deps, db, now):
    from langgraph.checkpoint.memory import MemorySaver

    from data.repositories.messages import MessageRepository
    from services.chat_service import ChatService

    deps = make_deps()
    service = ChatService(
        deps=deps, messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: service)
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: _plant_service(db, now))

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


def test_the_title_names_the_plant_being_discussed(app):
    """ "💬 Chat" alone gives no indication which plant the conversation is scoped
    to, which matters precisely because the page is reachable straight from the
    sidebar with whatever plant happens to be selected."""
    app.run()
    assert any("Basil" in t.value for t in app.title)


def test_chat_history_does_not_leak_across_plants(monkeypatch, make_deps, db, now):
    """The page used to read its own ``chat_plant_id``, set only by Plant detail's
    "Chat about this plant" button. Reaching Chat from the sidebar instead left that
    key pointing at whichever plant was opened first, so a second plant's page
    showed the first plant's transcript — and wrote new messages onto its rows.
    Reading ``selected_plant_id``, the same source of truth Plant detail uses,
    is what closes that."""
    from langgraph.checkpoint.memory import MemorySaver

    from data.db import transaction
    from data.repositories.messages import MessageRepository
    from services.chat_service import ChatService

    first = _create_plant(db, now, "Kitchen basil")
    second = _create_plant(db, now, "Office pothos")

    messages = MessageRepository(db)
    with transaction(db):
        messages.create(
            plant_id=first, role="user", content="A basil question.", tool_calls=None, now=now()
        )
        messages.create(
            plant_id=second, role="user", content="A pothos question.", tool_calls=None, now=now()
        )

    service = ChatService(deps=make_deps(), messages=messages, checkpointer=MemorySaver(), now=now)
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: service)
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: _plant_service(db, now))

    at = AppTest.from_file(str(_CHAT_PAGE), default_timeout=30)
    at.session_state["selected_plant_id"] = first
    at.run()
    rendered = [md.value for cm in at.chat_message for md in cm.markdown]
    assert any("basil question" in m.lower() for m in rendered)
    assert not any("pothos question" in m.lower() for m in rendered)
    assert any("Kitchen basil" in t.value for t in at.title)

    at.session_state["selected_plant_id"] = second
    at.run()

    assert not at.exception
    rendered = [md.value for cm in at.chat_message for md in cm.markdown]
    assert any("pothos question" in m.lower() for m in rendered)
    assert not any("basil question" in m.lower() for m in rendered)
    assert any("Office pothos" in t.value for t in at.title)


def test_persisted_tool_calls_render_collapsibly(monkeypatch, make_deps, db, now):
    """Design spec §5: "message history rendered with tool calls shown collapsibly"."""
    from langgraph.checkpoint.memory import MemorySaver

    from data.db import transaction
    from data.repositories.messages import MessageRepository
    from services.chat_service import ChatService

    plant_id = _create_plant(db, now, "Basil")
    messages = MessageRepository(db)
    with transaction(db):
        messages.create(
            plant_id=plant_id,
            role="assistant",
            content="Basil wants full sun.",
            tool_calls=[
                {
                    "name": "lookup_plant_care_profile",
                    "args": {"species": "Basil"},
                    "result": "Basil: full sun, evenly moist.",
                }
            ],
            now=now(),
        )

    service = ChatService(deps=make_deps(), messages=messages, checkpointer=MemorySaver(), now=now)
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: service)
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: _plant_service(db, now))

    at = AppTest.from_file(str(_CHAT_PAGE), default_timeout=30)
    at.session_state["selected_plant_id"] = plant_id
    at.run()

    assert not at.exception
    assert any("Tool calls" in e.label for e in at.expander)
    assert any("lookup_plant_care_profile" in m.value for m in at.markdown)
    assert any("full sun" in c.value for c in at.caption)


def _escalating_chat_service(db, now, make_deps, plant_id):
    from langchain_core.messages import AIMessage
    from langgraph.checkpoint.memory import MemorySaver

    from data.repositories.messages import MessageRepository
    from services.chat_service import ChatService
    from tests.fakes.chat_models import ScriptedToolCallingModel

    model = ScriptedToolCallingModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "suggest_new_diagnosis",
                        "args": {"reason": "new brown spots"},
                        "id": "call1",
                    }
                ],
            ),
            AIMessage(content="I've flagged this for a fresh look."),
        ]
    )
    return ChatService(
        deps=make_deps(chat_model=model),
        messages=MessageRepository(db),
        checkpointer=MemorySaver(),
        now=now,
    )


def test_escalation_offers_a_handoff_button_not_directions(monkeypatch, make_deps, db, now):
    """A diagnosis cannot start without photographs, so escalation hands the owner into
    the re-check upload flow instead of telling them to go find the button."""
    plant_id = _create_plant(db, now, "Basil")
    service = _escalating_chat_service(db, now, make_deps, plant_id)
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: service)
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: _plant_service(db, now))

    at = AppTest.from_file(str(_CHAT_PAGE), default_timeout=30)
    at.session_state["selected_plant_id"] = plant_id
    at.run()
    at.chat_input[0].set_value("There are new brown spots now, not yellowing.").run()

    assert not at.exception
    assert any("upload a new photo" in i.value.lower() for i in at.info)
    assert any(b.label == "Upload a new photo" for b in at.button)


def test_the_handoff_lands_on_plant_detail_with_the_upload_form_open(
    monkeypatch, make_deps, db, now, sample_plant, tmp_path
):
    """The whole point of the handoff: the owner must arrive at the upload form, not at
    plant_detail's default closed "Re-check this plant" state."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
    from services.diagnosis_service import DiagnosisService

    plant_service = _plant_service(db, now)
    chat_service = _escalating_chat_service(db, now, make_deps, sample_plant)
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: chat_service)
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: plant_service)

    chat = AppTest.from_file(str(_CHAT_PAGE), default_timeout=30)
    chat.session_state["selected_plant_id"] = sample_plant
    chat.run()
    chat.chat_input[0].set_value("There are new brown spots now, not yellowing.").run()
    next(b for b in chat.button if b.label == "Upload a new photo").click().run()

    # ``st.switch_page`` cannot resolve a page under AppTest — there is no
    # ``st.navigation`` registry, only the single script under test — so it raises here
    # where in the real app it navigates. The session state it primed beforehand is
    # what carries the handoff, and that is what the Plant detail page reads, so drive
    # that page with the primed state directly.
    primed = {
        key: chat.session_state[key]
        for key in ("selected_plant_id", "recheck_stage", "_recheck_owner_plant_id")
    }
    assert primed["recheck_stage"] == "upload"
    assert primed["selected_plant_id"] == sample_plant

    deps = make_deps()
    monkeypatch.setattr(
        "ui.bootstrap.get_service",
        lambda: DiagnosisService(
            deps, build_diagnosis_graph(deps, MemorySaver()), upload_dir=tmp_path
        ),
    )
    detail_page = AppTest.from_file(
        str(Path(__file__).resolve().parent.parent.parent / "ui" / "pages" / "plant_detail.py"),
        default_timeout=30,
    )
    for key, value in primed.items():
        detail_page.session_state[key] = value
    detail_page.run()

    assert not detail_page.exception
    assert detail_page.file_uploader, "landed on the closed state, not the upload form"
    assert not any(b.label == "Re-check this plant" for b in detail_page.button)
    # Arriving at the form starts nothing: the owner still has to supply photographs,
    # which is the whole reason chat can't run a diagnosis by itself.
    assert deps.chat_model.call_count == 0


def test_a_non_escalating_reply_clears_a_previous_handoff_offer(monkeypatch, make_deps, db, now):
    """The offer reflects the newest answer, not the high-water mark of the session."""
    from langchain_core.messages import AIMessage
    from langgraph.checkpoint.memory import MemorySaver

    from data.repositories.messages import MessageRepository
    from services.chat_service import ChatService
    from tests.fakes.chat_models import ScriptedToolCallingModel

    plant_id = _create_plant(db, now, "Basil")
    model = ScriptedToolCallingModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "suggest_new_diagnosis", "args": {"reason": "spots"}, "id": "c1"}
                ],
            ),
            AIMessage(content="I've flagged this for a fresh look."),
            AIMessage(content="Watering every other day is fine for a basil."),
        ]
    )
    service = ChatService(
        deps=make_deps(chat_model=model),
        messages=MessageRepository(db),
        checkpointer=MemorySaver(),
        now=now,
    )
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: service)
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: _plant_service(db, now))

    at = AppTest.from_file(str(_CHAT_PAGE), default_timeout=30)
    at.session_state["selected_plant_id"] = plant_id
    at.run()
    at.chat_input[0].set_value("New brown spots.").run()
    assert any(b.label == "Upload a new photo" for b in at.button)

    at.chat_input[0].set_value("How often should I water it?").run()

    assert not at.exception
    assert not any(b.label == "Upload a new photo" for b in at.button)


def test_a_plant_that_no_longer_exists_is_reported_not_crashed(monkeypatch, make_deps, db, now):
    from langgraph.checkpoint.memory import MemorySaver

    from data.repositories.messages import MessageRepository
    from services.chat_service import ChatService

    service = ChatService(
        deps=make_deps(), messages=MessageRepository(db), checkpointer=MemorySaver(), now=now
    )
    monkeypatch.setattr("ui.bootstrap.get_chat_service", lambda: service)
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: _plant_service(db, now))

    at = AppTest.from_file(str(_CHAT_PAGE), default_timeout=30)
    at.session_state["selected_plant_id"] = 999_999
    at.run()

    assert not at.exception
    assert any("no longer exists" in e.value for e in at.error)
