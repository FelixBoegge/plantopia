"""Renders a differential diagnosis as ranked cards."""

import streamlit as st

from agent.schemas import Differential

_SEVERITY_BADGE = {
    "act_today": "🔴 Act today",
    "act_this_week": "🟡 Act this week",
    "monitor": "🟢 Monitor",
}


def render_differential(differential: Differential, *, low_confidence: bool) -> None:
    """Render the diagnosis. Never presents a low-confidence result as a conclusion."""
    if differential.is_healthy:
        st.success("This plant looks healthy. I could not find a problem worth treating.")
        st.write(differential.reasoning)
        return

    if low_confidence:
        st.warning(
            "**I cannot tell you confidently what is wrong.** The evidence does not "
            "separate these possibilities. Each one below has a test you can run — that "
            "will narrow it down faster than any guess I could make."
        )

    for index, candidate in enumerate(differential.candidates):
        heading = f"{candidate.name} — {candidate.probability:.0%}"
        with st.container(border=True):
            st.subheader(heading if index else f"{heading} (most likely)")
            st.caption(_SEVERITY_BADGE.get(candidate.severity.value, candidate.severity.value))
            st.progress(candidate.probability)

            st.markdown("**How to confirm it**")
            st.info(candidate.distinguishing_test)

            left, right = st.columns(2)
            with left:
                st.markdown("**Points to it**")
                for evidence in candidate.supporting_evidence:
                    st.markdown(f"- {evidence}")
            with right:
                st.markdown("**Argues against it**")
                if candidate.contradicting_evidence:
                    for evidence in candidate.contradicting_evidence:
                        st.markdown(f"- {evidence}")
                else:
                    st.caption("Nothing observed argues against this.")

            if candidate.transmissible:
                st.warning("This can spread to nearby plants.")

    with st.expander("Reasoning"):
        st.write(differential.reasoning)
