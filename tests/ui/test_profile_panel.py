"""UI tests for the profile panel."""

import pytest

pytestmark = pytest.mark.ui


def test_an_empty_profile_says_so():
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.profile_panel import render_profile_panel

        render_profile_panel([], lambda fact: None)

    app = AppTest.from_function(script).run()
    assert not app.exception
    assert any("nothing" in c.value.lower() or "no facts" in c.value.lower() for c in app.caption)


def test_a_fact_shows_its_source_and_confidence():
    from streamlit.testing.v1 import AppTest

    def script():
        # AppTest.from_function execs only this function's own source in
        # isolation, so it must be self-contained — no closing over module-level
        # names such as WHEN.
        from datetime import UTC, datetime

        from data.repositories.profile import ProfileFact
        from ui.components.profile_panel import render_profile_panel

        when = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        render_profile_panel(
            [
                ProfileFact(
                    fact="lives in Berlin",
                    source="stated",
                    confidence=0.9,
                    first_seen=when,
                    last_confirmed=when,
                )
            ],
            lambda fact: None,
        )

    app = AppTest.from_function(script).run()
    body = " ".join(m.value for m in app.markdown) + " ".join(c.value for c in app.caption)
    assert "lives in Berlin" in body
    assert "stated" in body.lower()
    assert "0.9" in body or "90" in body


def test_a_populated_profile_explains_that_source_is_origin_not_current_standing():
    """A fact's `source` never upgrades from `inferred` to `stated` — the panel must
    say so, or the label reads as a claim about present-day confidence rather than
    where the fact was first learned."""
    from streamlit.testing.v1 import AppTest

    def script():
        from datetime import UTC, datetime

        from data.repositories.profile import ProfileFact
        from ui.components.profile_panel import render_profile_panel

        when = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        render_profile_panel(
            [
                ProfileFact(
                    fact="lives in Berlin",
                    source="stated",
                    confidence=0.9,
                    first_seen=when,
                    last_confirmed=when,
                )
            ],
            lambda fact: None,
        )

    app = AppTest.from_function(script).run()
    assert not app.exception
    captions = " ".join(c.value.lower() for c in app.caption)
    assert "origin" in captions or "how a fact was first learned" in captions


def test_clicking_forget_calls_on_delete_with_the_fact():
    """The delete control is the panel's whole reason to exist (spec: read-and-delete,
    not an editor). ``on_delete`` must receive the exact stored fact string, not a
    label or an index, since ``ProfileService.forget`` deletes by that string.

    ``on_delete`` records into ``st.session_state`` rather than a plain Python list
    closed over by the script — ``AppTest.from_function`` execs only the function's
    own source in isolation (see the note above), so a recording callable must live
    somewhere the rerun can see across script executions, and session state is exactly
    that.
    """
    from streamlit.testing.v1 import AppTest

    def script():
        from datetime import UTC, datetime

        import streamlit as st

        from data.repositories.profile import ProfileFact
        from ui.components.profile_panel import render_profile_panel

        deleted = st.session_state.setdefault("deleted", [])
        when = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        render_profile_panel(
            [
                ProfileFact(
                    fact="lives in Berlin",
                    source="stated",
                    confidence=0.9,
                    first_seen=when,
                    last_confirmed=when,
                )
            ],
            deleted.append,
        )

    app = AppTest.from_function(script).run()
    forget_button = next(b for b in app.button if b.label == "Forget")
    forget_button.click().run()
    assert app.session_state["deleted"] == ["lives in Berlin"]
