"""Tests for contagion assessment and roadmap construction."""

from agent.nodes.plan import make_build_roadmap, make_check_contagion
from agent.schemas import (
    Candidate,
    Differential,
    IPMTier,
    Roadmap,
    RoadmapStep,
    Severity,
    SpeciesGuess,
)
from agent.state import DiagnosisState
from tests.fakes.chat_models import FailingChatModel, ScriptedStructuredModel


def _candidate(disorder_id: str, probability: float, transmissible: bool) -> Candidate:
    return Candidate(
        disorder_id=disorder_id,
        name=disorder_id.replace("-", " ").title(),
        probability=probability,
        supporting_evidence=["stippling on leaf undersides"],
        contradicting_evidence=[],
        distinguishing_test="Tap a leaf over white paper and look for moving specks.",
        severity=Severity.ACT_TODAY,
        transmissible=transmissible,
    )


def _differential(*, transmissible: bool) -> Differential:
    return Differential(
        is_healthy=False,
        reasoning="r",
        candidates=[
            _candidate("spider-mites", 0.7, transmissible),
            _candidate("low-humidity", 0.2, False),
        ],
    )


def _state(images, **overrides) -> DiagnosisState:
    base = {
        "images": images,
        "plant_name": "Basil",
        "location_kind": "indoor",
        "species": SpeciesGuess(common_name="Basil", scientific_name=None, confidence=0.9),
        "differential": _differential(transmissible=True),
    }
    return DiagnosisState(**{**base, **overrides})


def _roadmap() -> Roadmap:
    return Roadmap(
        steps=[
            RoadmapStep(
                ordinal=1,
                action="Isolate the plant from every other plant today.",
                rationale="Mites spread by contact and air movement.",
                success_signal="No stippling appears on neighbouring plants.",
                tier=IPMTier.CULTURAL,
                day_offset=0,
            ),
            RoadmapStep(
                ordinal=2,
                action="Rinse both leaf surfaces thoroughly.",
                rationale="Physically removes adults and eggs.",
                success_signal="No new stippling on emerging leaves.",
                tier=IPMTier.MECHANICAL,
                day_offset=3,
            ),
        ]
    )


class TestCheckContagion:
    def test_transmissible_with_other_plants_flags_risk(self, make_deps, sample_images, db, now):
        from data.repositories.plants import PlantRepository

        PlantRepository(db).create(
            name="Monstera",
            species=None,
            species_confidence=None,
            location_kind="indoor",
            location_text=None,
            photo_ref=None,
            now=now(),
        )
        deps = make_deps()
        result = make_check_contagion(deps)(_state(sample_images))
        assert result["contagion"].at_risk is True
        assert "Monstera" in result["contagion"].advice

    def test_transmissible_with_no_other_plants_does_not_flag(self, make_deps, sample_images):
        deps = make_deps()
        result = make_check_contagion(deps)(_state(sample_images))
        assert result["contagion"].at_risk is False

    def test_non_transmissible_never_flags(self, make_deps, sample_images, db, now):
        from data.repositories.plants import PlantRepository

        PlantRepository(db).create(
            name="Monstera",
            species=None,
            species_confidence=None,
            location_kind="indoor",
            location_text=None,
            photo_ref=None,
            now=now(),
        )
        deps = make_deps()
        state = _state(sample_images, differential=_differential(transmissible=False))
        assert make_check_contagion(deps)(state)["contagion"].at_risk is False

    def test_the_plant_being_diagnosed_is_not_counted_as_at_risk(
        self, make_deps, sample_images, db, now
    ):
        from data.repositories.plants import PlantRepository

        plant_id = PlantRepository(db).create(
            name="Basil",
            species=None,
            species_confidence=None,
            location_kind="indoor",
            location_text=None,
            photo_ref=None,
            now=now(),
        )
        deps = make_deps()
        result = make_check_contagion(deps)(_state(sample_images, plant_id=plant_id))
        assert result["contagion"].at_risk is False

    def test_a_healthy_plant_gets_no_contagion_risk(self, make_deps, sample_images):
        healthy = Differential(is_healthy=True, candidates=[], reasoning="Fine.")
        deps = make_deps()
        result = make_check_contagion(deps)(_state(sample_images, differential=healthy))
        assert result["contagion"].at_risk is False

    def test_missing_differential_is_handled(self, make_deps, sample_images):
        deps = make_deps()
        result = make_check_contagion(deps)(_state(sample_images, differential=None))
        assert result["contagion"].at_risk is False


class TestBuildRoadmap:
    def test_records_the_roadmap(self, make_deps, sample_images):
        deps = make_deps(chat_model=ScriptedStructuredModel([_roadmap()]))
        result = make_build_roadmap(deps)(_state(sample_images))
        assert result["roadmap"] == _roadmap()

    def test_steps_are_ipm_ordered(self, make_deps, sample_images):
        deps = make_deps(chat_model=ScriptedStructuredModel([_roadmap()]))
        steps = make_build_roadmap(deps)(_state(sample_images))["roadmap"].steps
        assert [int(s.tier) for s in steps] == sorted(int(s.tier) for s in steps)

    def test_a_healthy_plant_gets_no_roadmap(self, make_deps, sample_images):
        healthy = Differential(is_healthy=True, candidates=[], reasoning="Fine.")
        model = ScriptedStructuredModel([])
        deps = make_deps(chat_model=model)
        result = make_build_roadmap(deps)(_state(sample_images, differential=healthy))
        assert result["roadmap"] is None
        assert model.call_count == 0

    def test_no_differential_means_no_roadmap(self, make_deps, sample_images):
        model = ScriptedStructuredModel([])
        deps = make_deps(chat_model=model)
        result = make_build_roadmap(deps)(_state(sample_images, differential=None))
        assert result["roadmap"] is None
        assert model.call_count == 0

    def test_contagion_advice_reaches_the_prompt(self, make_deps, sample_images):
        from agent.schemas import ContagionAssessment

        model = ScriptedStructuredModel([_roadmap()])
        deps = make_deps(chat_model=model)
        contagion = ContagionAssessment(at_risk=True, advice="Quarantine from Monstera today.")
        make_build_roadmap(deps)(_state(sample_images, contagion=contagion))
        assert "Quarantine" in str(model.prompts[0])

    def test_model_failure_leaves_the_roadmap_unset(self, make_deps, sample_images):
        """Better no plan than a fabricated one."""
        deps = make_deps(chat_model=FailingChatModel(RuntimeError("api down")))
        result = make_build_roadmap(deps)(_state(sample_images))
        assert result["roadmap"] is None
        assert result["errors"]
