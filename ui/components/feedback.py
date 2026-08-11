"""The treatment-outcome feedback prompt."""

from collections.abc import Callable

import streamlit as st

from data.repositories.feedback import DidItHelp

_OPTIONS: list[DidItHelp] = ["yes", "no", "unclear", "too_early"]


def render_feedback_prompt(
    *, on_submit: Callable[[int | None, DidItHelp | None, str | None], None]
) -> None:
    """Ask whether the treatment helped. Calls ``on_submit`` on the submit click."""
    st.subheader("Did this treatment help?")
    did_it_help = st.radio("", _OPTIONS, horizontal=True, label_visibility="collapsed")
    free_text = st.text_area("Anything else worth noting? (optional)")

    if st.button("Submit feedback"):
        on_submit(None, did_it_help, free_text)
