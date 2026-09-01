"""How much of a conversation reaches the model.

Asserted on the *property* — what the model is sent — rather than on how the middleware
achieves it. The middlewares are framework behaviour this project does not own, so an
upgrade that changed the mechanism but kept the behaviour should pass here, and one that
broke the behaviour should fail.

The model is a recording double: it captures the messages it was handed, which is the only
place this can be observed. Nothing here asserts on the stored transcript — that property
lives in `tests/unit/services/test_chat_transcript_is_untouched.py`, deliberately separate,
because the two must not be able to pass for the same reason.
"""

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.chat_agent import _context_limits
from core.config import Settings
from tests.secrets import TEST_JWT_SECRET

# What a real web-search result costs, measured from tests/fixtures/tavily_care_calathea.json:
# four passages, 5,262 characters. This is the thing that dominates a conversation.
A_SEARCH_RESULT = "x" * 5262

# And what a person and the agent actually say in the same turn, which is far less.
A_QUESTION = "Why are the lower leaves going yellow at the edges?"
AN_ANSWER = "The pattern points at the roots rather than the leaves themselves."


def _settings(**overrides) -> Settings:
    return Settings(
        jwt_secret=TEST_JWT_SECRET, openrouter_api_key="sk-test", _env_file=None, **overrides
    )


def _turns(count: int) -> list:
    """A conversation of ``count`` turns, each with a tool call and its result."""
    messages: list = []
    for turn in range(count):
        messages.append(HumanMessage(content=f"{A_QUESTION} ({turn})"))
        messages.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "web_search_plant_info",
                        "args": {"query": f"query {turn}"},
                        "id": f"call-{turn}",
                    }
                ],
            )
        )
        messages.append(
            ToolMessage(content=f"{A_SEARCH_RESULT} ({turn})", tool_call_id=f"call-{turn}")
        )
        messages.append(AIMessage(content=f"{AN_ANSWER} ({turn})"))
    return messages


def _after_editing(messages: list, settings: Settings) -> list:
    """The messages as the model would actually receive them.

    Driven through the middleware's own `wrap_model_call` with a handler that captures the
    request, rather than reaching past it into the edit — this is the real path, and it is
    the only place the property is observable. Running a whole agent to reach it would be
    asserting on the graph instead.
    """
    editing = _context_limits(settings)[0]
    seen: list[list] = []

    def _capture(request):
        seen.append(list(request.messages))
        return AIMessage(content="captured")

    editing.wrap_model_call(
        ModelRequest(
            model=None,
            messages=messages,
            system_message=None,
            tool_choice=None,
            tools=[],
            response_format=None,
            state={"messages": messages},
            runtime=None,
            model_settings={},
        ),
        _capture,
    )
    return seen[0]


def _size(messages: list) -> int:
    return sum(len(str(getattr(m, "content", ""))) for m in messages)


class TestTheMiddlewareIsWiredAtAll:
    """A guard on the guard. If the list stopped carrying these, every assertion below
    would be describing behaviour nothing was configured to produce."""

    def test_both_mechanisms_are_present(self):
        limits = _context_limits(_settings())

        names = [type(m).__name__ for m in limits]
        assert names == ["ContextEditingMiddleware", "SummarizationMiddleware"]

    def test_clearing_comes_before_summarising(self):
        """Order is the decision. Dropping stale tool output is free and removes most of the
        weight; summarising costs a model call, so it must be what runs when the cheap
        measure was not enough."""
        limits = _context_limits(_settings())

        assert type(limits[0]).__name__ == "ContextEditingMiddleware"

    def test_the_thresholds_come_from_settings(self):
        limits = _context_limits(
            _settings(chat_clear_tools_after_tokens=1234, chat_keep_recent_tool_results=7)
        )

        edit = limits[0].edits[0]
        assert edit.trigger == 1234
        assert edit.keep == 7


class TestAShortConversation:
    def test_is_passed_through_untouched(self):
        """Below the threshold nothing is dropped: a conversation that fits should be sent
        exactly as it happened."""
        messages = _turns(1)

        assert _after_editing(messages, _settings()) == messages

    def test_even_with_a_generous_threshold_and_several_turns(self):
        messages = _turns(3)

        kept = _after_editing(messages, _settings(chat_clear_tools_after_tokens=1_000_000))

        assert kept == messages


class TestALongConversation:
    def test_old_tool_output_stops_being_sent(self):
        messages = _turns(12)

        kept = _after_editing(messages, _settings())

        oldest = next(m for m in kept if isinstance(m, ToolMessage))
        assert A_SEARCH_RESULT not in str(oldest.content)

    def test_recent_tool_output_is_kept_whole(self):
        messages = _turns(12)

        kept = _after_editing(messages, _settings(chat_keep_recent_tool_results=3))

        results = [m for m in kept if isinstance(m, ToolMessage)]
        assert A_SEARCH_RESULT in str(results[-1].content)
        assert sum(A_SEARCH_RESULT in str(m.content) for m in results) == 3

    def test_the_model_can_tell_something_was_there(self):
        """Cleared rather than deleted. A model that saw no tool call at all might ask the
        same question again; one that sees a placeholder knows it already looked."""
        messages = _turns(12)

        kept = _after_editing(messages, _settings())

        oldest = next(m for m in kept if isinstance(m, ToolMessage))
        assert str(oldest.content).strip() != ""

    def test_what_was_said_is_never_dropped_by_this_mechanism(self):
        """Clearing touches tool output only. Everything a person and the agent said stays,
        which is why it can run first and for free."""
        messages = _turns(12)

        kept = _after_editing(messages, _settings())

        said = [str(m.content) for m in kept if not isinstance(m, ToolMessage)]
        assert any(f"{A_QUESTION} (0)" in s for s in said)
        assert any(f"{AN_ANSWER} (11)" in s for s in said)

    def test_the_tool_call_itself_survives(self):
        """`clear_tool_inputs=False`. The query is small and is what tells the model it has
        already asked something — which is exactly what stops it asking again."""
        messages = _turns(12)

        kept = _after_editing(messages, _settings())

        calls = [m for m in kept if isinstance(m, AIMessage) and m.tool_calls]
        assert calls
        assert calls[0].tool_calls[0]["args"] == {"query": "query 0"}


class TestItStopsGrowing:
    @pytest.mark.parametrize("turns", [10, 20, 40])
    def test_what_reaches_the_model_is_bounded(self, turns):
        """The property the whole change exists for: the size must not keep tracking the
        number of turns."""
        unbounded = _size(_turns(turns))
        bounded = _size(_after_editing(_turns(turns), _settings()))

        assert bounded < unbounded
        # Four turns' worth of search results would be generous; the setting keeps three.
        assert bounded < len(A_SEARCH_RESULT) * 4 + turns * 400

    def test_doubling_the_turns_does_not_double_the_context(self):
        twenty = _size(_after_editing(_turns(20), _settings()))
        forty = _size(_after_editing(_turns(40), _settings()))

        # Grows only by what was *said*, not by what was fetched.
        assert forty < twenty * 1.5


class TestTheBackstop:
    """Summarisation, which costs a model call and therefore fires much later."""

    def test_it_runs_on_the_cheap_tier(self, monkeypatch):
        """Condensing is a mechanical extraction, not a judgement about a plant. Paying
        reasoning-tier prices for something nobody reads would be paying for nothing."""
        from core.llm import build_gate_model, build_reasoning_model

        gate = build_gate_model()
        summariser = _context_limits(_settings())[1].model

        assert summariser.model_name == gate.model_name
        assert summariser.model_name != build_reasoning_model().model_name

    def test_its_threshold_is_far_above_the_clearing_one(self):
        """Order by cost. Clearing is free and removes most of the weight, so it must have
        every chance to be enough before a model call is spent."""
        settings = _settings()

        assert settings.chat_summarise_after_tokens > settings.chat_clear_tools_after_tokens * 2

    def test_it_keeps_recent_exchanges_verbatim(self):
        """An agent that summarised what was just said would be answering a paraphrase of
        the question."""
        limits = _context_limits(_settings(chat_keep_recent_messages=12))

        assert limits[1].keep == ("messages", 12)

    def test_its_threshold_comes_from_settings(self):
        limits = _context_limits(_settings(chat_summarise_after_tokens=4321))

        assert limits[1].trigger == ("tokens", 4321)
