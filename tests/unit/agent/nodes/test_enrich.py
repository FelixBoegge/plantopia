"""Tests for enrichment and its conditional tool calls.

These are the highest-value tests in the suite: they cover the decisions that make
this an agent rather than a pipeline of fixed calls.
"""

from agent.nodes.enrich import make_enrich
from agent.schemas import (
    CareProfile,
    Passage,
    Severity,
    SpeciesGuess,
    Symptom,
    SymptomPosition,
    SymptomSet,
    WeatherSummary,
)
from agent.state import DiagnosisState
from core.config import Settings


class _Spy:
    """Records calls so tests can assert a tool was or was not used."""

    def __init__(self, result=None):
        self.result = result
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class _StubRetriever:
    def __init__(self, passages: list[Passage], image_passages: list[Passage] | None = None):
        self.passages = passages
        self.image_passages = image_passages or []
        self.queries: list[list[str]] = []
        self.image_calls: list[int] = []

    def search(self, queries, k):
        self.queries.append(list(queries))
        return self.passages[:k]

    def search_by_image(self, images, k):
        self.image_calls.append(len(images))
        return self.image_passages[:k]


def _passage(score: float, doc_id: str = "root-rot") -> Passage:
    return Passage(doc_id=doc_id, section="Symptoms", text="brown mushy roots", score=score)


def _settings_with_thresholds() -> Settings:
    return Settings(
        openrouter_api_key="sk-test",
        retrieval_score_threshold=0.35,
        species_confidence_threshold=0.5,
        image_match_threshold=0.45,
    )


def _weather() -> WeatherSummary:
    return WeatherSummary(
        min_temp_c=-1.0,
        max_temp_c=12.0,
        total_precip_mm=40.0,
        frost_days=2,
        heat_days=0,
        days_covered=21,
    )


def _state(images, **overrides) -> DiagnosisState:
    base = {
        "images": images,
        "plant_name": "Basil",
        "location_kind": "indoor",
        "species": SpeciesGuess(common_name="Basil", scientific_name=None, confidence=0.9),
        "symptoms": SymptomSet(
            symptoms=[
                Symptom(
                    description="Yellowing",
                    position=SymptomPosition.LOWER_LEAVES,
                    severity=Severity.ACT_THIS_WEEK,
                )
            ],
            soil_condition="wet",
            overall_vigor="declining",
        ),
        "answers": {"watering": "twice a week"},
    }
    return DiagnosisState(**{**base, **overrides})


class TestRetrieval:
    def test_retrieved_passages_land_in_state(self, make_deps, sample_images):
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)]))
        result = make_enrich(deps)(_state(sample_images))
        assert result["retrieved"]

    def test_queries_are_built_from_the_symptoms(self, make_deps, sample_images):
        retriever = _StubRetriever([_passage(0.9)])
        deps = make_deps(retriever=retriever)
        make_enrich(deps)(_state(sample_images))
        assert any("Yellowing" in q for q in retriever.queries[0])

    def test_missing_symptoms_skips_retrieval(self, make_deps, sample_images):
        retriever = _StubRetriever([_passage(0.9)])
        deps = make_deps(retriever=retriever)
        result = make_enrich(deps)(_state(sample_images, symptoms=None))
        assert retriever.queries == []
        assert result["retrieved"] == []


class TestImagePath:
    """Cross-modal retrieval, and the separation it requires (spec §10.4)."""

    def _settings(self, **overrides) -> Settings:
        defaults = {
            "openrouter_api_key": "sk-test",
            "retrieval_score_threshold": 0.35,
            "species_confidence_threshold": 0.5,
            "image_match_threshold": 0.45,
        }
        return Settings(**{**defaults, **overrides})

    def test_the_photographs_are_embedded_and_searched(self, make_deps, sample_images):
        retriever = _StubRetriever([_passage(0.9)], [_passage(0.8, "spider-mites")])
        deps = make_deps(retriever=retriever, settings=self._settings())
        make_enrich(deps)(_state(sample_images))
        assert retriever.image_calls == [len(sample_images)]

    def test_visual_matches_land_in_their_own_field(self, make_deps, sample_images):
        visual = _passage(0.8, "spider-mites")
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.9)], [visual]), settings=self._settings()
        )
        result = make_enrich(deps)(_state(sample_images))
        assert result["visual_matches"] == [visual]

    def test_visual_matches_are_never_merged_into_retrieved(self, make_deps, sample_images):
        """Scores from the two paths are on different scales — merging corrupts ranking."""
        visual = _passage(0.8, "spider-mites")
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.9)], [visual]), settings=self._settings()
        )
        result = make_enrich(deps)(_state(sample_images))
        assert visual not in result["retrieved"]

    def test_weak_visual_matches_are_dropped(self, make_deps, sample_images):
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.9)], [_passage(0.1, "spider-mites")]),
            settings=self._settings(image_match_threshold=0.45),
        )
        assert make_enrich(deps)(_state(sample_images))["visual_matches"] == []

    def test_the_threshold_is_inclusive(self, make_deps, sample_images):
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.9)], [_passage(0.45, "spider-mites")]),
            settings=self._settings(image_match_threshold=0.45),
        )
        assert make_enrich(deps)(_state(sample_images))["visual_matches"]

    def test_a_weak_visual_match_does_not_open_the_escalation_gate(self, make_deps, sample_images):
        """The gate reads text scores only, or it would fire on every diagnosis."""
        search = _Spy([])
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.9)], [_passage(0.05, "spider-mites")]),
            web_search=search,
            settings=self._settings(),
        )
        result = make_enrich(deps)(_state(sample_images))
        assert search.calls == []
        assert result["escalated_to_web"] is False

    def test_a_strong_visual_match_does_not_suppress_escalation(self, make_deps, sample_images):
        """Equally, a good visual match must not mask weak text retrieval."""
        search = _Spy([])
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.05)], [_passage(0.95, "spider-mites")]),
            web_search=search,
            settings=self._settings(),
        )
        assert make_enrich(deps)(_state(sample_images))["escalated_to_web"] is True

    def test_an_empty_image_path_leaves_the_text_path_untouched(self, make_deps, sample_images):
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)], []), settings=self._settings())
        result = make_enrich(deps)(_state(sample_images))
        assert result["visual_matches"] == []
        assert result["retrieved"]

    def test_the_image_tool_is_recorded(self, make_deps, sample_images):
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.9)], [_passage(0.8)]),
            settings=self._settings(),
        )
        assert "search_by_photograph" in make_enrich(deps)(_state(sample_images))["tools_used"]

    def test_the_image_path_runs_even_without_extracted_symptoms(self, make_deps, sample_images):
        """Its whole value is not depending on the symptom description."""
        retriever = _StubRetriever([_passage(0.9)], [_passage(0.8, "spider-mites")])
        deps = make_deps(retriever=retriever, settings=self._settings())
        result = make_enrich(deps)(_state(sample_images, symptoms=None))
        assert retriever.queries == []
        assert result["visual_matches"]


class TestWeather:
    def test_indoor_plant_does_not_trigger_a_weather_call(self, make_deps, sample_images):
        weather = _Spy(_weather())
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)]), weather=weather)
        make_enrich(deps)(_state(sample_images, location_kind="indoor"))
        assert weather.calls == []

    def test_outdoor_plant_with_a_location_triggers_a_weather_call(self, make_deps, sample_images):
        weather = _Spy(_weather())
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)]), weather=weather)
        result = make_enrich(deps)(
            _state(sample_images, location_kind="outdoor", location_text="Berlin")
        )
        assert weather.calls
        assert result["weather"] == _weather()

    def test_outdoor_location_can_come_from_the_answers(self, make_deps, sample_images):
        weather = _Spy(_weather())
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)]), weather=weather)
        state = _state(
            sample_images,
            location_kind="outdoor",
            answers={"watering": "weekly", "location": "Lisbon"},
        )
        make_enrich(deps)(state)
        assert weather.calls[0][0] == "Lisbon"

    def test_outdoor_plant_without_a_location_skips_weather(self, make_deps, sample_images):
        weather = _Spy(_weather())
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)]), weather=weather)
        make_enrich(deps)(_state(sample_images, location_kind="outdoor"))
        assert weather.calls == []

    def test_a_weather_failure_does_not_fail_the_node(self, make_deps, sample_images):
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)]), weather=_Spy(None))
        result = make_enrich(deps)(
            _state(sample_images, location_kind="outdoor", location_text="Berlin")
        )
        assert result["weather"] is None
        assert result["retrieved"]


class TestWebEscalation:
    def _settings(self) -> Settings:
        return Settings(
            openrouter_api_key="sk-test",
            retrieval_score_threshold=0.35,
            species_confidence_threshold=0.5,
        )

    def test_strong_retrieval_does_not_escalate(self, make_deps, sample_images):
        search = _Spy([])
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.9)]),
            web_search=search,
            settings=self._settings(),
        )
        result = make_enrich(deps)(_state(sample_images))
        assert search.calls == []
        assert result["escalated_to_web"] is False

    def test_weak_retrieval_escalates(self, make_deps, sample_images):
        search = _Spy([_passage(0.7, doc_id="web:example.org")])
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.1)]),
            web_search=search,
            settings=self._settings(),
        )
        result = make_enrich(deps)(_state(sample_images))
        assert search.calls
        assert result["escalated_to_web"] is True

    def test_unknown_species_escalates_despite_good_retrieval(self, make_deps, sample_images):
        search = _Spy([])
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.95)]),
            web_search=search,
            settings=self._settings(),
        )
        unknown = SpeciesGuess(common_name="Unknown", scientific_name=None, confidence=0.0)
        make_enrich(deps)(_state(sample_images, species=unknown))
        assert search.calls

    def test_web_passages_are_appended_to_retrieved(self, make_deps, sample_images):
        web = _passage(0.7, doc_id="web:example.org")
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.1)]),
            web_search=_Spy([web]),
            settings=self._settings(),
        )
        result = make_enrich(deps)(_state(sample_images))
        assert web in result["retrieved"]

    def test_a_web_search_failure_leaves_curated_results_intact(self, make_deps, sample_images):
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.1)]),
            web_search=_Spy([]),
            settings=self._settings(),
        )
        result = make_enrich(deps)(_state(sample_images))
        assert result["retrieved"]


class TestCareBaseline:
    def test_known_species_looks_up_a_care_profile(self, make_deps, sample_images):
        profile = CareProfile(
            species="Basil",
            light="full sun",
            water="evenly moist",
            temperature_c=(18, 30),
            humidity="average",
        )
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)]), care_profile=_Spy(profile))
        result = make_enrich(deps)(_state(sample_images))
        assert result["care_baseline_text"]
        assert "full sun" in result["care_baseline_text"]

    def test_unknown_species_skips_the_lookup(self, make_deps, sample_images):
        lookup = _Spy(None)
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)]), care_profile=lookup)
        unknown = SpeciesGuess(common_name="Unknown", scientific_name=None, confidence=0.0)
        result = make_enrich(deps)(_state(sample_images, species=unknown))
        assert lookup.calls == []
        assert result["care_baseline_text"] is None


class TestToolRecording:
    def test_every_tool_used_is_recorded(self, make_deps, sample_images):
        profile = CareProfile(
            species="Basil",
            light="full sun",
            water="moist",
            temperature_c=(18, 30),
            humidity="average",
        )
        deps = make_deps(
            retriever=_StubRetriever([_passage(0.9)]),
            weather=_Spy(_weather()),
            care_profile=_Spy(profile),
        )
        result = make_enrich(deps)(
            _state(sample_images, location_kind="outdoor", location_text="Berlin")
        )
        assert "search_plant_knowledge" in result["tools_used"]
        assert "get_local_weather" in result["tools_used"]
        assert "lookup_plant_care_profile" in result["tools_used"]

    def test_unused_tools_are_not_recorded(self, make_deps, sample_images):
        deps = make_deps(retriever=_StubRetriever([_passage(0.9)]))
        result = make_enrich(deps)(_state(sample_images))
        assert "get_local_weather" not in result["tools_used"]
        assert "web_search_plant_info" not in result["tools_used"]
