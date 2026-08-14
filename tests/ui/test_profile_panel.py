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
