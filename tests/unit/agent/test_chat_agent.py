"""Tests for the plant-scoped chat agent's tool wrapping and prompt construction."""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from agent.chat_agent import make_chat_agent
from data.repositories.plants import PlantRepository


def test_raises_for_an_unknown_plant(make_deps, db):
    deps = make_deps()
    with pytest.raises(ValueError, match="No plant"):
        make_chat_agent(deps, 999_999, MemorySaver())


def test_builds_an_agent_for_a_known_plant(make_deps, db, now):
    plant_id = PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    deps = make_deps()
    agent, escalation = make_chat_agent(deps, plant_id, MemorySaver())
    assert agent is not None
    assert escalation == {}


def test_the_agent_is_compiled_with_the_checkpointer_it_was_given(make_deps, db, now):
    """A ``create_agent`` graph compiled without a checkpointer silently ignores
    ``thread_id``, which is exactly how the chat loop lost its memory. Assert the
    compiled graph actually holds one rather than trusting the call site."""
    plant_id = PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    checkpointer = MemorySaver()
    agent, _ = make_chat_agent(make_deps(), plant_id, checkpointer)
    assert agent.checkpointer is checkpointer


def test_every_tool_gets_a_clean_model_visible_name(make_deps, db, now):
    """The Python function needs a ``_tool`` suffix to avoid shadowing the imported
    ``search_plant_knowledge``, but the name the model reads should not carry it —
    ``@tool`` defaults to the function name unless given one explicitly."""
    from agent.chat_agent import _make_tools

    plant_id = PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    tools, _ = _make_tools(make_deps(), plant_id)

    names = sorted(t.name for t in tools)
    assert names == [
        "get_local_weather",
        "get_plant_journal",
        "lookup_plant_care_profile",
        "search_plant_knowledge",
        "suggest_new_diagnosis",
        "web_search_plant_info",
    ]
    assert not any(name.endswith("_tool") for name in names)


def test_the_care_profile_tool_reports_an_unknown_species(make_deps, db, now):
    from agent.chat_agent import _make_tools

    plant_id = PlantRepository(db).create(
        name="Mystery plant",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    deps = make_deps(care_profile=lambda species: None)
    tools, _ = _make_tools(deps, plant_id)
    care_tool = next(t for t in tools if t.name == "lookup_plant_care_profile")
    assert "no baseline" in care_tool.invoke({"species": "Mystery plant"}).lower()


def test_the_weather_tool_reports_when_it_cannot_run(make_deps, db, now):
    from agent.chat_agent import _make_tools

    plant_id = PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="outdoor",
        location_text="Berlin",
        photo_ref=None,
        now=now(),
    )
    deps = make_deps(weather=lambda location, days: None)
    tools, _ = _make_tools(deps, plant_id)
    weather_tool = next(t for t in tools if t.name == "get_local_weather")
    assert "could not" in weather_tool.invoke({"location": "Berlin"}).lower()


def test_the_journal_tool_reports_no_history_for_a_fresh_plant(make_deps, db, now):
    from agent.chat_agent import _make_tools

    plant_id = PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    deps = make_deps()
    tools, _ = _make_tools(deps, plant_id)
    journal_tool = next(t for t in tools if t.name == "get_plant_journal")
    assert "no history" in journal_tool.invoke({}).lower()


def test_the_journal_tool_aggregates_observations_diagnoses_and_roadmap_steps(
    make_deps, db, now, sample_plant
):
    """``sample_plant`` seeds one observation, one diagnosis (Overwatering leading,
    Root rot second), and two roadmap steps — one marked done, one still pending.
    The journal must surface all three sources, not just diagnoses.
    """
    from agent.chat_agent import _make_tools

    deps = make_deps()
    tools, _ = _make_tools(deps, sample_plant)
    journal_tool = next(t for t in tools if t.name == "get_plant_journal")
    journal = journal_tool.invoke({}).lower()

    assert "observation" in journal
    assert "overwatering" in journal
    assert "stop watering" in journal
    assert "repot" in journal
    assert "done" in journal
    assert "pending" in journal


def test_suggest_new_diagnosis_populates_the_escalation_dict(make_deps, db, now):
    from agent.chat_agent import _make_tools

    plant_id = PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    deps = make_deps()
    tools, escalation = _make_tools(deps, plant_id)
    escalate_tool = next(t for t in tools if t.name == "suggest_new_diagnosis")
    escalate_tool.invoke({"reason": "new brown spots, not yellowing"})
    assert escalation == {"reason": "new brown spots, not yellowing"}
