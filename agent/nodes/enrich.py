"""Enrichment: gather the evidence a diagnosis needs.

Every tool call here is conditional. Weather is irrelevant to a plant on a kitchen
windowsill; the web is unnecessary when the curated corpus already answered. Deciding
which evidence this case needs is the agentic part of the pipeline, so each decision
is recorded in ``tools_used`` for the trace and the UI.
"""

import logging

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.schemas import LoadedImage
from agent.state import DiagnosisState
from tools.knowledge import build_symptom_queries, search_plant_knowledge
from tools.web_search import should_escalate

logger = logging.getLogger(__name__)

WEATHER_DAYS_BACK = 21
KNOWLEDGE_RESULTS = 6
VISUAL_RESULTS = 4


def make_enrich(deps: Deps) -> NodeFn:
    """Retrieve grounding knowledge and any conditionally relevant context."""

    def enrich(state: DiagnosisState) -> dict:
        tools_used: list[str] = []

        passages = _retrieve(deps, state, tools_used)
        visual = _retrieve_by_image(deps, state, tools_used)
        weather = _fetch_weather(deps, state, tools_used)
        care_text = _care_baseline(deps, state, tools_used)

        # The escalation gate reads the TEXT path only. Cross-modal scores sit on a
        # lower scale, so including them would open the gate on nearly every
        # diagnosis and buy a web search we do not need (spec §10.4).
        passages, escalated = _maybe_escalate(deps, state, passages, tools_used)

        return {
            "retrieved": passages,
            "visual_matches": visual,
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


def _retrieve_by_image(deps: Deps, state: DiagnosisState, tools_used: list[str]) -> list:
    """Retrieve by embedding the photographs directly (spec §10.4).

    This path does not depend on ``assess_symptoms``. The text path searches for a
    *description* of the symptoms, so it inherits any mistake the vision model made
    writing that description; this path bypasses it. The two fail independently,
    which is the entire reason for running both.

    Weak matches are dropped rather than shown. A cross-modal score near the floor
    means the photograph did not resemble anything in the corpus, and passing that to
    the diagnose prompt as 'evidence' would be worse than passing nothing.
    """
    if not state.images:
        return []

    # Asked of the retriever rather than of settings: what matters is whether this
    # search can happen, not why. Reporting it as a tool used when no image embedder
    # is wired tells the owner a second opinion was sought that never was.
    if not deps.retriever.supports_image_search:
        return []

    # Bytes are resolved here, at the one node that needs them, and go no further.
    # A photograph missing from the store drops out of the visual search rather than
    # failing the diagnosis: this path is corroboration, and the text path stands on
    # its own. The vision call treats the same absence as fatal, because there it is.
    loaded = []
    for image in state.images:
        data = deps.blobs.get(deps.user_id, image.ref)
        if data is None:
            logger.warning("photograph %s is not in the store; skipping it", image.ref)
            continue
        loaded.append(LoadedImage(data=data, media_type=image.media_type))
    if not loaded:
        return []

    tools_used.append("search_by_photograph")
    matches = deps.retriever.search_by_image(loaded, k=VISUAL_RESULTS)
    kept = [p for p in matches if p.score >= deps.settings.image_match_threshold]

    if matches and not kept:
        logger.info(
            "dropped %d visual matches below the %.2f threshold",
            len(matches),
            deps.settings.image_match_threshold,
        )
    return kept


def _fetch_weather(deps: Deps, state: DiagnosisState, tools_used: list[str]):
    """Fetch recent weather, but only for an outdoor plant with a known location."""
    if state.location_kind != "outdoor":
        return None

    location = state.location_text or state.answers.get("location")
    if not location:
        return None

    tools_used.append("get_local_weather")
    # Anchored on when the photograph was taken, where it said. Without this the window is
    # the three weeks before the *upload*, which for anybody who did not upload immediately
    # is three weeks the plant partly did not live through.
    taken = state.captured_at.date() if state.captured_at else None
    return deps.weather(location, WEATHER_DAYS_BACK, taken)


def _care_baseline(deps: Deps, state: DiagnosisState, tools_used: list[str]) -> str | None:
    """Look up what normal looks like for this species, if we know the species."""
    if not state.species_name or state.species_name == "Unknown":
        return None

    tools_used.append("lookup_plant_care_profile")
    profile = deps.care_profile(state.species_name)
    if profile is None:
        return None

    low, high = profile.temperature_c
    return (
        f"Typical requirements for {profile.species}: "
        f"light — {profile.light}; water — {profile.water}; "
        f"temperature — {low}–{high} °C; humidity — {profile.humidity}."
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
