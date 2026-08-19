"""Tests for the chat provenance panel.

An answer that silently blends the knowledge base, this plant's history, live weather
and the open web cannot be weighed by the reader — "your basil has root rot" reads the
same whether it came from a corpus passage or from nothing at all.
"""

import pytest

pytestmark = pytest.mark.ui


def test_no_tool_calls_renders_nothing():
    """An answer the model gave unaided must not sprout an empty "Consulted" line —
    the whole point is that a grounded answer looks different from an ungrounded one."""
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.tool_calls import render_tool_calls

        render_tool_calls(None)
        render_tool_calls([])

    app = AppTest.from_function(script).run()

    assert not app.exception
    assert not app.caption
    assert not app.expander


def test_sources_are_named_for_the_owner_not_the_function():
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.tool_calls import render_tool_calls

        render_tool_calls(
            [{"name": "get_plant_journal", "args": {}, "result": "2026-01-01: Diagnosis"}]
        )

    app = AppTest.from_function(script).run()

    body = " ".join([*(c.value for c in app.caption), *(m.value for m in app.markdown)])
    assert "This plant's history" in body
    assert "get_plant_journal" not in body


def test_the_summary_is_visible_without_expanding():
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.tool_calls import render_tool_calls

        render_tool_calls([{"name": "web_search_plant_info", "args": {"query": "rust"}}])

    app = AppTest.from_function(script).run()

    assert any("Consulted" in c.value and "Web search" in c.value for c in app.caption)


def test_a_source_used_repeatedly_is_named_once_in_the_summary():
    """Three knowledge-base searches in one turn are one source. "knowledge base,
    knowledge base, knowledge base" tells the reader nothing the first mention did."""
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.tool_calls import render_tool_calls

        render_tool_calls(
            [
                {"name": "search_plant_knowledge", "args": {"query": "a"}},
                {"name": "search_plant_knowledge", "args": {"query": "b"}},
                {"name": "get_local_weather", "args": {"location": "Berlin"}},
            ]
        )

    app = AppTest.from_function(script).run()

    summary = next(c.value for c in app.caption if "Consulted" in c.value)
    assert summary.count("Plant knowledge base") == 1
    assert "Local weather" in summary
    # The detail list still shows every call — the dedup is for the summary only.
    assert any("3" in e.label for e in app.expander)


def test_an_unknown_tool_still_appears_under_its_own_name():
    """A tool added later should look unpolished, not invisible: a missing label must
    not silently drop a source from the provenance."""
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.tool_calls import render_tool_calls

        render_tool_calls([{"name": "consult_the_oracle", "args": {}}])

    app = AppTest.from_function(script).run()

    body = " ".join([*(c.value for c in app.caption), *(m.value for m in app.markdown)])
    assert "consult_the_oracle" in body


def test_the_escalation_tool_is_listed_like_any_other():
    """It retrieves nothing, but it is why the page offers a re-check — hiding it would
    make that offer appear from nowhere."""
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.tool_calls import render_tool_calls

        render_tool_calls([{"name": "suggest_new_diagnosis", "args": {"reason": "new spots"}}])

    app = AppTest.from_function(script).run()

    body = " ".join([*(c.value for c in app.caption), *(m.value for m in app.markdown)])
    assert "new diagnosis" in body.lower()


def test_a_call_that_returned_nothing_says_so():
    """Silence from a tool is information: it distinguishes "the web had nothing" from
    "the agent never looked"."""
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.tool_calls import render_tool_calls

        render_tool_calls([{"name": "get_local_weather", "args": {}, "result": ""}])

    app = AppTest.from_function(script).run()

    assert any("returned nothing" in c.value for c in app.caption)
