"""UI tests for the cost badge."""

import pytest

pytestmark = pytest.mark.ui


def test_renders_tokens_and_cost():
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.cost_badge import render_cost_badge

        render_cost_badge(
            {"prompt_tokens": 1240, "completion_tokens": 890, "total_tokens": 2130}, 0.0043
        )

    app = AppTest.from_function(script).run()
    caption = app.caption[0].value
    assert "1,240 in" in caption
    assert "890 out" in caption
    assert "$0.0043" in caption


def test_renders_tokens_only_when_cost_is_unknown():
    """A provider that omits cost must not produce a fabricated $0.00 (spec §5)."""
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.cost_badge import render_cost_badge

        render_cost_badge(
            {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}, None
        )

    app = AppTest.from_function(script).run()
    caption = app.caption[0].value
    assert "100 in" in caption
    assert "$" not in caption


def test_renders_nothing_when_no_usage_was_recorded():
    """Every diagnosis written before Phase 3 has NULL usage."""
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.cost_badge import render_cost_badge

        render_cost_badge(None, None)

    app = AppTest.from_function(script).run()
    assert len(app.caption) == 0
