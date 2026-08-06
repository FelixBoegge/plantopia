"""Tests for the escalation gate and the Tavily web-search tool."""

import httpx
import respx

from agent.schemas import Passage
from core.config import Settings
from tools.web_search import TAVILY_URL, should_escalate, web_search_plant_info


def _settings(**overrides) -> Settings:
    defaults = {
        "openrouter_api_key": "sk-test",
        "retrieval_score_threshold": 0.35,
        "species_confidence_threshold": 0.50,
    }
    return Settings(**{**defaults, **overrides})


def _passage(score: float) -> Passage:
    return Passage(doc_id="root-rot", section="Symptoms", text="...", score=score)


class TestEscalationGate:
    def test_escalates_when_no_passages_were_retrieved(self):
        assert should_escalate([], species_confidence=0.9, settings=_settings()) is True

    def test_escalates_when_the_best_score_is_below_threshold(self):
        assert should_escalate([_passage(0.2)], 0.9, _settings()) is True

    def test_escalates_when_species_confidence_is_below_threshold(self):
        assert should_escalate([_passage(0.9)], 0.1, _settings()) is True

    def test_does_not_escalate_when_both_signals_are_strong(self):
        assert should_escalate([_passage(0.9)], 0.9, _settings()) is False

    def test_uses_the_best_score_not_the_first(self):
        passages = [_passage(0.2), _passage(0.8)]
        assert should_escalate(passages, 0.9, _settings()) is False

    def test_threshold_is_inclusive_at_the_boundary(self):
        settings = _settings(retrieval_score_threshold=0.5)
        assert should_escalate([_passage(0.5)], 0.9, settings) is False

    def test_thresholds_are_configurable(self):
        strict = _settings(retrieval_score_threshold=0.95)
        assert should_escalate([_passage(0.9)], 0.99, strict) is True


class TestWebSearch:
    @respx.mock
    def test_returns_passages_with_web_provenance(self):
        respx.post(TAVILY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Root rot guide",
                            "url": "https://example.org/root-rot",
                            "content": "Brown mushy roots indicate rot.",
                            "score": 0.88,
                        }
                    ]
                },
            )
        )
        passages = web_search_plant_info("root rot", api_key="tvly-test")
        assert len(passages) == 1
        assert passages[0].doc_id == "web:example.org"
        assert passages[0].section == "Root rot guide"
        assert "mushy" in passages[0].text

    @respx.mock
    def test_respects_max_results(self):
        respx.post(TAVILY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": f"t{i}",
                            "url": f"https://example.org/{i}",
                            "content": "c",
                            "score": 0.5,
                        }
                        for i in range(10)
                    ]
                },
            )
        )
        assert len(web_search_plant_info("q", api_key="tvly-test", max_results=3)) == 3

    def test_returns_empty_without_an_api_key(self):
        with respx.mock:
            assert web_search_plant_info("root rot", api_key=None) == []

    @respx.mock
    def test_api_error_returns_empty_rather_than_raising(self):
        respx.post(TAVILY_URL).mock(return_value=httpx.Response(500))
        assert web_search_plant_info("q", api_key="tvly-test") == []

    @respx.mock
    def test_timeout_returns_empty(self):
        respx.post(TAVILY_URL).mock(side_effect=httpx.TimeoutException("slow"))
        assert web_search_plant_info("q", api_key="tvly-test") == []

    @respx.mock
    def test_malformed_payload_returns_empty(self):
        respx.post(TAVILY_URL).mock(return_value=httpx.Response(200, json={"unexpected": 1}))
        assert web_search_plant_info("q", api_key="tvly-test") == []

    @respx.mock
    def test_out_of_range_scores_are_clamped(self):
        respx.post(TAVILY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"title": "t", "url": "https://x.org/a", "content": "c", "score": 4.2}
                    ]
                },
            )
        )
        assert web_search_plant_info("q", api_key="tvly-test")[0].score == 1.0

    def test_blank_query_returns_empty(self):
        with respx.mock:
            assert web_search_plant_info("  ", api_key="tvly-test") == []
