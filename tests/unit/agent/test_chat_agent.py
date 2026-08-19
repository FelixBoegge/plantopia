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


def test_the_chat_system_prompt_carries_the_profile(make_deps, sample_plant):
    from agent.chat_agent import build_chat_system_prompt

    deps = make_deps(profile_facts=lambda: "- tends to overwater (confidence 0.7)")
    prompt = build_chat_system_prompt(deps, sample_plant)

    assert "tends to overwater" in prompt


def test_the_chat_system_prompt_is_unchanged_when_the_profile_is_empty(make_deps, sample_plant):
    from agent.chat_agent import build_chat_system_prompt

    with_empty = build_chat_system_prompt(make_deps(profile_facts=lambda: ""), sample_plant)
    with_facts = build_chat_system_prompt(
        make_deps(profile_facts=lambda: "- lives in Berlin (confidence 0.9)"), sample_plant
    )

    assert "lives in Berlin" in with_facts
    assert with_facts.startswith(with_empty), "the profile block must be appended, not interleaved"


def test_an_unknown_plant_still_raises(make_deps):
    import pytest

    from agent.chat_agent import build_chat_system_prompt

    with pytest.raises(ValueError, match="No plant"):
        build_chat_system_prompt(make_deps(profile_facts=lambda: ""), 9999)


def test_a_raising_profile_read_does_not_break_the_chat_turn(make_deps, sample_plant):
    """`deps.profile_facts()` resolves to a separate sqlite connection; if that read
    raises, the chat turn must still get a system prompt rather than fail."""
    from agent.chat_agent import build_chat_system_prompt

    def _boom():
        raise RuntimeError("profile db is locked")

    prompt = build_chat_system_prompt(make_deps(profile_facts=_boom), sample_plant)

    assert "Plant:" in prompt


class TestDeadEndsNameTheNextStep:
    """A tool result the model reads is a place to steer it.

    Observed with strawberries: the care-profile list has nothing for them, the tool
    said only "no baseline care profile is known", and the agent answered from its own
    training data rather than searching. A miss that names the next tool is the cheapest
    available fix — no extra model call, no prompt the model might skim past.
    """

    def _tool(self, deps, plant_id, name):
        from agent.chat_agent import _make_tools

        tools, _ = _make_tools(deps, plant_id)
        return next(t for t in tools if t.name == name)

    def test_a_care_profile_miss_points_at_the_web_search(self, make_deps, sample_plant):
        tool = self._tool(
            make_deps(care_profile=lambda species: None), sample_plant, "lookup_plant_care_profile"
        )

        result = tool.invoke({"species": "Fragaria x ananassa"})

        assert "web_search_plant_info" in result
        assert "houseplants only" in result, "a miss must not read as 'nothing is known'"

    def test_an_empty_knowledge_base_points_at_the_web_search(self, make_deps, sample_plant):
        """The corpus holds disorders only, so a care question finding nothing there is
        expected rather than a dead end."""

        class _Empty:
            def search(self, queries, k, *, sections=None):
                return []

            def sections_for(self, doc_ids, sections):
                return []

        tool = self._tool(make_deps(retriever=_Empty()), sample_plant, "search_plant_knowledge")

        result = tool.invoke({"query": "how do I care for strawberries"})

        assert "web_search_plant_info" in result
        assert "disorders only" in result

    def test_an_empty_web_search_asks_for_the_admission_instead(self, make_deps, sample_plant):
        """The web is the last resort, so this one has no further tool to name. It asks
        the agent to say the answer is unsourced, which is what the provenance panel
        cannot show on its own."""
        tool = self._tool(make_deps(web_search=lambda q: []), sample_plant, "web_search_plant_info")

        result = tool.invoke({"query": "strawberry care"})

        assert "own knowledge" in result
        assert "tell the owner" in result


class TestGroundingInstructions:
    """The prompt said nothing about which tool suits which question, so a broad care
    question went to the care-profile lookup and stopped there."""

    def test_the_prompt_sends_broad_care_questions_to_the_web(self, make_deps, sample_plant):
        from agent.chat_agent import build_chat_system_prompt

        prompt = build_chat_system_prompt(make_deps(), sample_plant)

        assert "web search" in prompt.lower()
        assert "An empty result is not an answer." in prompt

    def test_the_prompt_requires_owning_up_to_an_unsourced_answer(self, make_deps, sample_plant):
        """It pairs with the provenance panel: a reply with no sources listed should say
        it was not looked up, rather than looking indistinguishable from one that was."""
        from agent.chat_agent import build_chat_system_prompt

        prompt = build_chat_system_prompt(make_deps(), sample_plant)

        assert "your own knowledge" in prompt

    def test_the_prompt_still_forbids_re_searching_what_it_has(self, make_deps, sample_plant):
        """Pushing towards tools must not turn into searching the same thing every turn:
        the web search costs money and latency."""
        from agent.chat_agent import build_chat_system_prompt

        prompt = build_chat_system_prompt(make_deps(), sample_plant)

        assert "Do not re-search" in prompt
