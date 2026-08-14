"""Tests for the Pydantic contracts. These validators are the guarantees that
every node test relies on."""

import pytest
from pydantic import ValidationError

from agent.schemas import (
    Candidate,
    Differential,
    IPMTier,
    Roadmap,
    RoadmapStep,
    Severity,
    SpeciesGuess,
    Symptom,
    SymptomPosition,
    SymptomSet,
)


def _candidate(disorder_id: str = "root-rot", probability: float = 0.7) -> Candidate:
    return Candidate(
        disorder_id=disorder_id,
        name="Root rot",
        probability=probability,
        supporting_evidence=["soil is wet", "lower leaves yellowing"],
        contradicting_evidence=[],
        distinguishing_test="Slide the plant from its pot and check for brown, mushy roots.",
        severity=Severity.ACT_TODAY,
        transmissible=False,
    )


def _step(ordinal: int, tier: IPMTier, day_offset: int = 0) -> RoadmapStep:
    return RoadmapStep(
        ordinal=ordinal,
        action="Stop watering until the top 3 cm of soil is dry.",
        rationale="Reduces the anaerobic conditions root rot needs.",
        success_signal="No new yellowing leaves within a week.",
        tier=tier,
        day_offset=day_offset,
    )


class TestSpeciesGuess:
    def test_confidence_must_be_a_probability(self):
        with pytest.raises(ValidationError):
            SpeciesGuess(common_name="Basil", scientific_name=None, confidence=1.4)

    def test_scientific_name_is_optional(self):
        guess = SpeciesGuess(common_name="Unknown", scientific_name=None, confidence=0.1)
        assert guess.scientific_name is None


class TestSymptomSet:
    def test_requires_at_least_one_symptom(self):
        with pytest.raises(ValidationError):
            SymptomSet(symptoms=[], soil_condition="wet", overall_vigor="poor")

    def test_position_is_required_on_every_symptom(self):
        with pytest.raises(ValidationError):
            Symptom(description="yellowing", severity=Severity.MONITOR)  # type: ignore[call-arg]

    def test_accepts_a_valid_set(self):
        symptoms = SymptomSet(
            symptoms=[
                Symptom(
                    description="Yellowing",
                    position=SymptomPosition.LOWER_LEAVES,
                    severity=Severity.ACT_THIS_WEEK,
                )
            ],
            soil_condition="wet to the touch",
            overall_vigor="declining",
        )
        assert symptoms.symptoms[0].position is SymptomPosition.LOWER_LEAVES


class TestCandidate:
    def test_probability_bounded(self):
        with pytest.raises(ValidationError):
            _candidate(probability=1.2)

    def test_distinguishing_test_cannot_be_trivial(self):
        with pytest.raises(ValidationError):
            Candidate(
                disorder_id="x",
                name="X",
                probability=0.5,
                supporting_evidence=["a"],
                contradicting_evidence=[],
                distinguishing_test="look",
                severity=Severity.MONITOR,
                transmissible=False,
            )

    def test_supporting_evidence_required(self):
        with pytest.raises(ValidationError):
            Candidate(
                disorder_id="x",
                name="X",
                probability=0.5,
                supporting_evidence=[],
                contradicting_evidence=[],
                distinguishing_test="A sufficiently long distinguishing test.",
                severity=Severity.MONITOR,
                transmissible=False,
            )


class TestDifferential:
    def test_requires_two_to_three_candidates_when_not_healthy(self):
        with pytest.raises(ValidationError):
            Differential(is_healthy=False, candidates=[_candidate()], reasoning="r")

    def test_rejects_more_than_three_candidates(self):
        candidates = [_candidate(f"d{i}", 0.9 - i * 0.1) for i in range(4)]
        with pytest.raises(ValidationError):
            Differential(is_healthy=False, candidates=candidates, reasoning="r")

    def test_rejects_unsorted_candidates(self):
        candidates = [_candidate("a", 0.3), _candidate("b", 0.8)]
        with pytest.raises(ValidationError, match="descending"):
            Differential(is_healthy=False, candidates=candidates, reasoning="r")

    def test_healthy_differential_must_have_no_candidates(self):
        with pytest.raises(ValidationError):
            Differential(is_healthy=True, candidates=[_candidate()], reasoning="r")

    def test_healthy_differential_is_valid_when_empty(self):
        differential = Differential(is_healthy=True, candidates=[], reasoning="Looks fine.")
        assert differential.top_confidence == 0.0

    def test_top_confidence_is_the_first_probability(self):
        differential = Differential(
            is_healthy=False,
            candidates=[_candidate("a", 0.8), _candidate("b", 0.2)],
            reasoning="r",
        )
        assert differential.top_confidence == 0.8


class TestRoadmap:
    def test_ordinals_must_start_at_one_and_be_sequential(self):
        with pytest.raises(ValidationError, match="sequential"):
            Roadmap(steps=[_step(1, IPMTier.CULTURAL), _step(3, IPMTier.MECHANICAL)])

    def test_ipm_tiers_must_not_decrease(self):
        with pytest.raises(ValidationError, match="escalat"):
            Roadmap(steps=[_step(1, IPMTier.CHEMICAL), _step(2, IPMTier.CULTURAL)])

    def test_accepts_non_decreasing_tiers(self):
        roadmap = Roadmap(
            steps=[
                _step(1, IPMTier.CULTURAL),
                _step(2, IPMTier.CULTURAL, day_offset=3),
                _step(3, IPMTier.MECHANICAL, day_offset=7),
            ]
        )
        assert len(roadmap.steps) == 3

    def test_requires_at_least_one_step(self):
        with pytest.raises(ValidationError):
            Roadmap(steps=[])


class TestProgressVerdict:
    def test_accepts_each_valid_verdict(self):
        from agent.schemas import ProgressVerdict

        for verdict in ("improving", "static", "worsening", "new_problem"):
            ProgressVerdict(verdict=verdict, reasoning="Because the symptoms changed.")

    def test_rejects_an_unknown_verdict(self):
        from pydantic import ValidationError

        from agent.schemas import ProgressVerdict

        with pytest.raises(ValidationError):
            ProgressVerdict(verdict="cured", reasoning="x")

    def test_reasoning_cannot_be_empty(self):
        from pydantic import ValidationError

        from agent.schemas import ProgressVerdict

        with pytest.raises(ValidationError):
            ProgressVerdict(verdict="improving", reasoning="")


def test_an_extracted_fact_rejects_an_empty_string():
    from pydantic import ValidationError

    from agent.schemas import ExtractedFact

    with pytest.raises(ValidationError):
        ExtractedFact(fact="", source="stated", confidence=0.8)


def test_an_extracted_fact_rejects_an_essay():
    """A 'durable fact' that runs to a paragraph is a summary, not a fact."""
    from pydantic import ValidationError

    from agent.schemas import ExtractedFact

    with pytest.raises(ValidationError):
        ExtractedFact(fact="x" * 201, source="inferred", confidence=0.5)


def test_a_profile_update_defaults_to_three_empty_buckets():
    from agent.schemas import ProfileUpdate

    update = ProfileUpdate()
    assert update.confirmed == []
    assert update.added == []
    assert update.superseded == []
