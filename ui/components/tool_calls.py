"""Show where a chat answer's information came from.

An answer that silently blends the knowledge base, this plant's own history, live
weather and the open web is impossible to weigh: "your basil has root rot" reads the
same whether it came from a corpus passage or from nothing at all. This renders the
provenance of every turn — a one-line summary that needs no clicking, and the calls
themselves underneath for anyone who wants to check.

Sources are named as the owner would name them, not as the functions are named. A
reader deciding how much to trust an answer cares that it consulted this plant's
history; ``get_plant_journal`` is an implementation detail.
"""

from typing import Any

import streamlit as st

# Tool name -> (icon, what the owner would call it). A tool missing from here still
# renders, under its own name: a new tool should look unpolished, not invisible.
_SOURCES: dict[str, tuple[str, str]] = {
    "search_plant_knowledge": ("📚", "Plant knowledge base"),
    "get_plant_journal": ("📋", "This plant's history"),
    "lookup_plant_care_profile": ("🌱", "Species care profile"),
    "get_local_weather": ("🌦️", "Local weather"),
    "web_search_plant_info": ("🌐", "Web search"),
    "suggest_new_diagnosis": ("🔍", "Flagged for a new diagnosis"),
}


def describe_source(name: str) -> tuple[str, str]:
    """The icon and owner-facing label for a tool, falling back to its raw name."""
    return _SOURCES.get(name, ("🔧", name or "unknown tool"))


def render_tool_calls(tool_calls: list[dict[str, Any]] | None) -> None:
    """Render one turn's provenance: a visible summary, then the calls in detail.

    The summary is deliberately not inside the expander. Provenance that only appears
    once clicked is provenance most readers never see, and the point of showing it is
    that an answer grounded in the corpus should be distinguishable at a glance from
    one the model produced unaided.

    ``suggest_new_diagnosis`` is listed like any other call. It retrieves nothing, but
    it is the most consequential thing the agent can do in a conversation — it is why
    the page offers a re-check — and hiding it would make that offer appear from
    nowhere.
    """
    if not tool_calls:
        return

    # Deduplicated, in the order first used: the model may search the knowledge base
    # three times in one turn, and "knowledge base, knowledge base, knowledge base"
    # tells the reader nothing the first mention did not.
    seen: dict[str, str] = {}
    for call in tool_calls:
        icon, label = describe_source(str(call.get("name", "")))
        seen.setdefault(label, icon)

    st.caption("Consulted " + " · ".join(f"{icon} {label}" for label, icon in seen.items()))

    with st.expander(f"What it looked up ({len(tool_calls)})"):
        for call in tool_calls:
            icon, label = describe_source(str(call.get("name", "")))
            st.markdown(f"{icon} **{label}**")

            args = call.get("args") or {}
            if args:
                # The query or location the agent chose, which is often the most
                # revealing part: it shows what the agent thought the question was.
                st.caption(", ".join(f"{key}: {value}" for key, value in args.items()))

            result = str(call.get("result") or "").strip()
            if result:
                st.code(result, language=None, wrap_lines=True)
            else:
                st.caption("_returned nothing_")
