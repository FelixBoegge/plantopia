"""The treatment-outcome feedback prompt."""

from collections.abc import Callable

import streamlit as st

from data.repositories.feedback import DidItHelp

_OPTIONS: list[DidItHelp] = ["yes", "no", "unclear", "too_early"]


def render_feedback_prompt(
    *, on_submit: Callable[[int | None, DidItHelp | None, str | None], None]
) -> None:
    """Ask whether the treatment helped. Calls ``on_submit`` on the submit click.

    The star rating is optional — ``feedback.rating`` is nullable, and someone who
    only wants to answer the yes/no question shouldn't be blocked. ``st.feedback``
    returns a 0-based index, so it is shifted into the 1-5 the column's
    ``CHECK (rating BETWEEN 1 AND 5)`` constraint accepts.
    """
    st.subheader("Did this treatment help?")
    # The label is spelled out rather than left empty so a screen reader announces
    # something; the visual design keeps it hidden under the subheader above.
    did_it_help = st.radio(
        "How did it go?", _OPTIONS, horizontal=True, label_visibility="collapsed"
    )
    st.caption("How would you rate the outcome? (optional)")
    stars = st.feedback("stars")
    free_text = st.text_area("Anything else worth noting? (optional)")

    if st.button("Submit feedback"):
        on_submit(None if stars is None else stars + 1, did_it_help, free_text)
