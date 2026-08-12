"""The plant-scoped chat agent.

A ReAct loop (``langchain.agents.create_agent``), not a fixed graph — follow-up
conversation has no predictable shape, unlike the diagnosis pipeline (PLAN.md §5.1).
"""

from datetime import datetime

from langchain.agents import create_agent
from langchain_core.tools import tool

from agent.deps import Deps
from tools.knowledge import search_plant_knowledge

_SYSTEM_PROMPT_TEMPLATE = """You are a knowledgeable, plain-spoken plant-care
assistant, scoped to a single plant. Never falsely reassuring, never
catastrophising.

Plant: {name} ({species})
Setting: {location_kind}
Most recent diagnosis: {latest_diagnosis}

If the owner describes symptoms materially different from the most recent
diagnosis, call ``suggest_new_diagnosis`` rather than guessing from the
conversation alone — a text description cannot substitute for looking at the
plant."""


def make_chat_agent(deps: Deps, plant_id: int) -> tuple:
    """Build a ReAct agent scoped to one plant.

    Returns:
        A ``(agent, escalation)`` pair. ``escalation`` is a dict that
        ``suggest_new_diagnosis`` populates with a ``"reason"`` key if the agent
        calls it during the run that follows; empty otherwise.

    Raises:
        ValueError: if no plant exists with ``plant_id``.
    """
    plant = deps.plants.get(plant_id)
    if plant is None:
        raise ValueError(f"No plant with id {plant_id!r}.")

    latest = deps.diagnoses.latest_for_plant(plant_id)
    if latest is None:
        latest_summary = "None yet."
    elif latest.differential.is_healthy:
        latest_summary = "Healthy, no problem found."
    else:
        latest_summary = (
            f"{latest.differential.primary.name} ({latest.differential.primary.probability:.0%})"
        )

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        name=plant.name,
        species=plant.species or "unidentified",
        location_kind=plant.location_kind,
        latest_diagnosis=latest_summary,
    )

    tools, escalation = _make_tools(deps, plant_id)
    agent = create_agent(deps.chat_model, tools=tools, system_prompt=system_prompt)
    return agent, escalation


def _make_tools(deps: Deps, plant_id: int) -> tuple[list, dict]:
    """Build the tool list and its escalation dict together.

    Returned as a pair rather than an attribute on the list: a plain ``list`` has
    no ``__dict__``, so it cannot carry an extra attribute.
    """

    @tool
    def get_local_weather(location: str, days_back: int = 21) -> str:
        """Get a summary of recent weather at a named location."""
        summary = deps.weather(location, days_back)
        if summary is None:
            return "Weather could not be retrieved for that location."
        return (
            f"Over the last {summary.days_covered} days: low {summary.min_temp_c}C, "
            f"high {summary.max_temp_c}C, {summary.total_precip_mm}mm rain, "
            f"{summary.frost_days} frost day(s), {summary.heat_days} heat day(s)."
        )

    @tool
    def web_search_plant_info(query: str) -> str:
        """Search the web for plant-health information not in the curated corpus."""
        passages = deps.web_search(query)
        if not passages:
            return "No web results were found."
        return "\n\n".join(f"[{p.doc_id}] {p.text}" for p in passages)

    @tool
    def lookup_plant_care_profile(species: str) -> str:
        """Look up baseline light/water/temperature/humidity requirements for a species."""
        profile = deps.care_profile(species)
        if profile is None:
            return f"No baseline care profile is known for {species!r}."
        low, high = profile.temperature_c
        return (
            f"{profile.species}: light — {profile.light}; water — {profile.water}; "
            f"temperature — {low}-{high}C; humidity — {profile.humidity}."
        )

    @tool
    def search_plant_knowledge_tool(query: str) -> str:
        """Search the curated disorder knowledge base for information relevant to a
        described symptom or question."""
        passages = search_plant_knowledge(deps.retriever, [query], k=4)
        if not passages:
            return "Nothing relevant was found in the knowledge base."
        return "\n\n".join(f"[{p.doc_id} - {p.section}] {p.text}" for p in passages)

    @tool
    def get_plant_journal() -> str:
        """Read this plant's full observation, diagnosis, and roadmap history."""
        observations = deps.observations.list_for_plant(plant_id)
        diagnoses = deps.diagnoses.list_for_plant(plant_id)
        roadmap_steps = deps.roadmap.list_for_plant(plant_id)
        if not observations and not diagnoses and not roadmap_steps:
            return "No history recorded for this plant."

        events: list[tuple[datetime, str]] = []
        for o in observations:
            notes = f' — "{o.user_notes}"' if o.user_notes else ""
            events.append(
                (o.created_at, f"Observation ({o.kind}, {len(o.photo_refs)} photo(s)){notes}")
            )
        for d in diagnoses:
            outcome = "healthy" if d.differential.is_healthy else d.differential.primary.name
            events.append((d.created_at, f"Diagnosis: {outcome}"))
        for s in roadmap_steps:
            completed = f", completed {s.completed_at.date()}" if s.completed_at else ""
            events.append(
                (s.due_date, f"Roadmap step {s.ordinal} ({s.status}{completed}): {s.action}")
            )

        events.sort(key=lambda event: event[0])
        return "\n".join(f"- {when.date()}: {text}" for when, text in events)

    escalation: dict[str, str] = {}

    @tool
    def suggest_new_diagnosis(reason: str) -> str:
        """Call this when the owner describes symptoms materially different from the
        current diagnosis. This does not diagnose anything itself — it flags that a
        fresh set of photos is needed, which the owner supplies through the
        re-check flow."""
        escalation["reason"] = reason
        return (
            "I've flagged this for a fresh look — please use the Re-check button on "
            "this plant's page and upload a current photo, since I can't judge new "
            "symptoms from a description alone."
        )

    tools = [
        get_local_weather,
        web_search_plant_info,
        lookup_plant_care_profile,
        search_plant_knowledge_tool,
        get_plant_journal,
        suggest_new_diagnosis,
    ]
    return tools, escalation
