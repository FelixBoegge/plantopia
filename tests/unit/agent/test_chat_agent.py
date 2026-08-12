"""Tests for the plant-scoped chat agent's tool wrapping and prompt construction."""

import pytest

from agent.chat_agent import make_chat_agent
from data.repositories.plants import PlantRepository


def test_raises_for_an_unknown_plant(make_deps, db):
    deps = make_deps()
    with pytest.raises(ValueError, match="No plant"):
        make_chat_agent(deps, plant_id=999_999)


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
    agent, escalation = make_chat_agent(deps, plant_id=plant_id)
    assert agent is not None
    assert escalation == {}


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
