"""The re-check flow's bare (unscoped-by-plant) session-state keys.

Shared by ``plant_detail.py`` (which resets them on arrival for a different plant,
closing the cross-plant leak U7 describes) and ``chat.py`` (which resets them as part
of handing an escalation into the re-check upload form). Both sites need the same set
cleared; a single list is what keeps them from drifting apart the way the escalation
handoff and the plant-switch reset once did — the handoff popped ``recheck_result``
but not ``recheck_attempt``, a duplicate that had no way to learn about the other's
keys once it was written.
"""

import streamlit as st

RECHECK_STATE_KEYS = ("recheck_stage", "recheck_result", "recheck_attempt")


def clear_recheck_state() -> None:
    """Pop every bare re-check key. Callers set ``_recheck_owner_plant_id`` and/or
    ``recheck_stage`` themselves afterward, per their own needs."""
    for key in RECHECK_STATE_KEYS:
        st.session_state.pop(key, None)
