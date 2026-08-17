"""Plantopia — an AI plant-health agent."""

import streamlit as st

from core.config import get_settings
from core.tracing import configure_tracing

# "wide" rather than the default centred column: My Plants is a grid of cards, each
# holding a portrait photograph beside its details, and a centred column squeezed
# three of those into roughly half the browser window.
st.set_page_config(page_title="Plantopia", page_icon="🌿", layout="wide")


@st.cache_resource
def _configure_tracing_once() -> bool:
    """Enable LangSmith tracing exactly once for the life of the process.

    This module reruns top to bottom on every Streamlit rerun — every widget
    interaction on every page, not just navigation — so the call below would fire
    (and log) repeatedly without ``st.cache_resource``: the decorator is what turns
    "called on every rerun" into "the body runs once", the same trick
    ``ui/bootstrap.py``'s cached factories rely on. Living here, ahead of
    ``st.navigation(...).run()``, means tracing is live before *any* page — including
    Chat, which never touches ``get_service()`` at all — rather than only after the
    Diagnose page happens to be opened (spec §2.4/§5).

    Only ``core.config`` and ``core.tracing`` are imported to make this possible;
    neither pulls in LangGraph, Chroma, or the model clients that ``ui/bootstrap.py``
    needs, so this stays cheap even though it runs before any of that is wired.
    """
    return configure_tracing(get_settings())


_configure_tracing_once()

pages = [
    st.Page("ui/pages/my_plants.py", title="My Plants", icon="🌿", default=True),
    st.Page("ui/pages/diagnose.py", title="Diagnose", icon="🔍"),
    st.Page("ui/pages/plant_detail.py", title="Plant detail", icon="📋"),
    st.Page("ui/pages/chat.py", title="Chat", icon="💬"),
    st.Page("ui/pages/profile.py", title="What we've learned", icon="🧠"),
    st.Page("ui/pages/evaluation.py", title="Evaluation", icon="📊"),
]

selected = st.navigation(pages)

# Whether this rerun is the first one after navigating somewhere new. Every rerun
# re-executes this file, so a page cannot tell "the user just arrived" from "the user
# clicked something" on its own; comparing here, at the one place navigation is
# resolved, means no page has to remember to report where it is — and a page added
# later cannot forget to.
st.session_state.arrived_on_page = st.session_state.get("current_page") != selected.url_path
st.session_state.current_page = selected.url_path

selected.run()
