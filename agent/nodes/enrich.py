"""Enrichment: gather the evidence a diagnosis needs.

Every tool call here is conditional. Weather is irrelevant to a plant on a kitchen
windowsill; the web is unnecessary when the curated corpus already answered. Deciding
which evidence this case needs is the agentic part of the pipeline, so each decision
is recorded in ``tools_used`` for the trace and the UI.
"""

import logging

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.schemas import CareOrigin
from agent.state import DiagnosisState
from tools.knowledge import build_symptom_queries, search_plant_knowledge
from tools.web_search import should_escalate

logger = logging.getLogger(__name__)

WEATHER_DAYS_BACK = 21
KNOWLEDGE_RESULTS = 6


def make_enrich(deps: Deps) -> NodeFn:
    """Retrieve grounding knowledge and any conditionally relevant context."""

    def enrich(state: DiagnosisState) -> dict:
        tools_used: list[str] = []

        passages = _retrieve(deps, state, tools_used)
        weather = fetch_weather(deps, state, tools_used)
        care_text = _care_baseline(deps, state, tools_used)

        passages, escalated = _maybe_escalate(deps, state, passages, tools_used)

        return {
            "retrieved": passages,
            "weather": weather,
            "care_baseline_text": care_text,
            "escalated_to_web": escalated,
            "tools_used": [*state.tools_used, *tools_used],
        }

    return enrich


def _retrieve(deps: Deps, state: DiagnosisState, tools_used: list[str]) -> list:
    """Search the curated corpus, and look up whatever ``hypothesise`` named.

    Nothing to search on without symptoms — but a hypothesis is still worth fetching
    if one somehow exists, so the two conditions are separate.
    """
    queries = (
        build_symptom_queries(state.symptoms, state.species_name)
        if state.symptoms is not None
        else []
    )
    if not queries and not state.hypotheses:
        return []

    tools_used.append("search_plant_knowledge")
    return search_plant_knowledge(
        deps.retriever, queries, k=KNOWLEDGE_RESULTS, hypotheses=state.hypotheses
    )


def fetch_weather(deps: Deps, state: DiagnosisState, tools_used: list[str]):
    """Fetch recent weather, but only for an outdoor plant with a known location.

    Shared with the re-check path. It used to live only here, and `enrich` is skipped
    entirely by a re-check that is improving or static — so those runs recorded an
    observation with no weather, and a plant's history drew a graph for its first diagnosis
    and nothing beside the ones after it.
    """
    if state.location_kind != "outdoor":
        return None

    # The answer first. It is what the person left in the field at the pause, which is
    # either the place read from their photograph, the location the plant already had, or
    # the correction they typed over one of those — and a correction that lost to a stored
    # value would be a correction nobody could make.
    location = state.answers.get("location") or state.location_text
    if not location:
        return None

    tools_used.append("get_local_weather")
    # Anchored on when the photograph was taken, where it said. Without this the window is
    # the three weeks before the *upload*, which for anybody who did not upload immediately
    # is three weeks the plant partly did not live through.
    taken = state.captured_at.date() if state.captured_at else None
    return deps.weather(location, WEATHER_DAYS_BACK, taken, _position_if_accepted(state))


def _position_if_accepted(state: DiagnosisState) -> tuple[float, float] | None:
    """The photograph's position, but only where the name it produced was left alone.

    A position that becomes a name and is then resolved back into a position has been
    round-tripped through a geocoder to arrive where it started. So where the owner accepted
    the name, the position is used directly.

    Where they *changed* it, the name wins and this returns nothing. A correction that lost
    to the coordinates behind it would be a control that does nothing: somebody fixes a wrong
    town, watches the diagnosis proceed on the wrong weather anyway, and has no way to tell.

    Compared against what this run offered — `detected_place` — rather than against anything
    a client sent or anything re-derived later. A naming service that answered differently
    the second time would otherwise turn an accepted name into a corrected one.
    """
    if state.latitude is None or state.longitude is None or not state.detected_place:
        return None

    answered = (state.answers.get("location") or "").strip()
    if answered.casefold() != state.detected_place.strip().casefold():
        return None

    return (state.latitude, state.longitude)


def _care_baseline(deps: Deps, state: DiagnosisState, tools_used: list[str]) -> str | None:
    """Look up what normal looks like for this species, if we know the species."""
    if not state.species_name or state.species_name == "Unknown":
        return None

    tools_used.append("lookup_plant_care_profile")
    profile = deps.care_profile(state.species_name)
    if profile is None:
        return None

    low, high = profile.temperature_c
    baseline = (
        f"Typical requirements for {profile.species}: "
        f"light — {profile.light}; water — {profile.water}; "
        f"temperature — {low}–{high} °C; humidity — {profile.humidity}."
    )
    if profile.origin is not CareOrigin.RESEARCHED:
        return baseline

    # One clause, not a section. A model told the baseline was assembled from a web search
    # rather than written by a person should weight it slightly less against an observation
    # that contradicts it — which is the whole practical difference between the two tiers.
    return (
        f"{baseline} (This baseline was researched from web sources rather than curated, "
        "so prefer the observed symptoms where the two disagree.)"
    )


def _maybe_escalate(
    deps: Deps,
    state: DiagnosisState,
    passages: list,
    tools_used: list[str],
) -> tuple[list, bool]:
    """Fall back to web search when the corpus was not good enough.

    This gate is the concrete answer to "when RAG, when search": the curated corpus is
    authoritative and reproducible so it goes first; the web is current but unvetted
    so it is a labelled fallback.
    """
    if not should_escalate(passages, state.species_confidence, deps.settings):
        return passages, False

    query = _escalation_query(state)
    tools_used.append("web_search_plant_info")
    web_passages = deps.web_search(query)

    logger.info("escalated to web search: %d additional passages", len(web_passages))
    return [*passages, *web_passages], True


def _escalation_query(state: DiagnosisState) -> str:
    species = state.species_name or "unidentified plant"
    if state.symptoms:
        symptoms = ", ".join(s.description for s in state.symptoms.symptoms)
    else:
        symptoms = "unwell"
    return f"{species} {symptoms}"
