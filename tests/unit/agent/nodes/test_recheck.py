"""Tests for the re-check nodes: comparing progress and revising the roadmap."""

from agent.nodes.recheck import make_compare_progress, make_revise_roadmap
from agent.schemas import (
    Candidate,
    Differential,
    IPMTier,
    ProgressVerdict,
    Roadmap,
    RoadmapStep,
    Severity,
    Symptom,
    SymptomPosition,
    SymptomSet,
)
from agent.state import DiagnosisState
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.roadmap import RoadmapRepository
from tests.fakes.chat_models import FailingChatModel, ScriptedStructuredModel


def _differential() -> Differential:
    return Differential(
        is_healthy=False,
        reasoning="Wet soil and lower-leaf yellowing.",
        candidates=[
            Candidate(
                disorder_id="overwatering",
                name="Overwatering",
                probability=0.7,
                supporting_evidence=["wet soil"],
                contradicting_evidence=[],
                distinguishing_test="Feel the soil three days after watering.",
                severity=Severity.ACT_THIS_WEEK,
                transmissible=False,
            ),
            Candidate(
                disorder_id="root-rot",
                name="Root rot",
                probability=0.3,
                supporting_evidence=["wet soil"],
                contradicting_evidence=[],
                distinguishing_test="Unpot the plant and inspect the roots.",
                severity=Severity.ACT_TODAY,
                transmissible=False,
            ),
        ],
    )


def _prior_plant(db, now) -> tuple[int, int]:
    plant_id = PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    obs_id = ObservationRepository(db).create(
        plant_id=plant_id, kind="initial", photo_refs=["img-1"], user_notes=None, now=now()
    )
    diagnosis_id = DiagnosisRepository(db).create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=None,
        retrieved=[],
        model="test-model",
        now=now(),
    )
    RoadmapRepository(db).create_from_roadmap(
        diagnosis_id=diagnosis_id,
        plant_id=plant_id,
        roadmap=Roadmap(
            steps=[
                RoadmapStep(
                    ordinal=1,
                    action="Stop watering until the top 3 cm is dry.",
                    rationale="Lets the roots breathe.",
                    success_signal="No new yellow leaves.",
                    tier=IPMTier.CULTURAL,
                    day_offset=0,
                )
            ]
        ),
        now=now(),
    )
    return plant_id, diagnosis_id


def _state(images, plant_id, **overrides) -> DiagnosisState:
    base = {
        "images": images,
        "plant_name": "Basil",
        "location_kind": "indoor",
        "plant_id": plant_id,
        "symptoms": SymptomSet(
            symptoms=[
                Symptom(
                    description="Fewer yellow leaves",
                    position=SymptomPosition.LOWER_LEAVES,
                    severity=Severity.MONITOR,
                )
            ],
            soil_condition="drier",
            overall_vigor="good",
        ),
    }
    return DiagnosisState(**{**base, **overrides})


class TestCompareProgress:
    def test_records_the_models_verdict(self, make_deps, sample_images, db, now):
        plant_id, _ = _prior_plant(db, now)
        verdict = ProgressVerdict(verdict="improving", reasoning="Fewer symptoms than before.")
        deps = make_deps(chat_model=ScriptedStructuredModel([verdict]))
        result = make_compare_progress(deps)(_state(sample_images, plant_id))
        assert result["verdict"] == verdict

    def test_the_prior_differential_reaches_the_prompt(self, make_deps, sample_images, db, now):
        plant_id, _ = _prior_plant(db, now)
        model = ScriptedStructuredModel([ProgressVerdict(verdict="static", reasoning="Unchanged.")])
        deps = make_deps(chat_model=model)
        make_compare_progress(deps)(_state(sample_images, plant_id))
        assert "Overwatering" in str(model.prompts[0])

    def test_roadmap_completion_status_reaches_the_prompt(self, make_deps, sample_images, db, now):
        plant_id, _ = _prior_plant(db, now)
        model = ScriptedStructuredModel([ProgressVerdict(verdict="static", reasoning="Unchanged.")])
        deps = make_deps(chat_model=model)
        make_compare_progress(deps)(_state(sample_images, plant_id))
        assert "pending" in str(model.prompts[0])

    def test_no_prior_diagnosis_is_treated_as_a_new_problem(
        self, make_deps, sample_images, db, now
    ):
        plant_id = PlantRepository(db).create(
            name="Basil",
            species="Basil",
            species_confidence=0.9,
            location_kind="indoor",
            location_text=None,
            photo_ref=None,
            now=now(),
        )
        deps = make_deps(chat_model=ScriptedStructuredModel([]))
        result = make_compare_progress(deps)(_state(sample_images, plant_id))
        assert result["verdict"].verdict == "new_problem"

    def test_model_failure_is_treated_as_a_new_problem_not_a_crash(
        self, make_deps, sample_images, db, now
    ):
        plant_id, _ = _prior_plant(db, now)
        deps = make_deps(chat_model=FailingChatModel(RuntimeError("api down")))
        result = make_compare_progress(deps)(_state(sample_images, plant_id))
        assert result["verdict"].verdict == "new_problem"
        assert result["errors"]


class TestReviseRoadmap:
    def test_records_the_revised_roadmap(self, make_deps, sample_images, db, now):
        plant_id, _ = _prior_plant(db, now)
        revised = Roadmap(
            steps=[
                RoadmapStep(
                    ordinal=1,
                    action="Continue the current watering schedule.",
                    rationale="It is working.",
                    success_signal="No new yellow leaves in a week.",
                    tier=IPMTier.CULTURAL,
                    day_offset=7,
                )
            ]
        )
        deps = make_deps(chat_model=ScriptedStructuredModel([revised]))
        state = _state(
            sample_images,
            plant_id,
            verdict=ProgressVerdict(verdict="improving", reasoning="Better."),
        )
        result = make_revise_roadmap(deps)(state)
        assert result["roadmap"] == revised

    def test_carries_the_prior_differential_forward_unchanged(
        self, make_deps, sample_images, db, now
    ):
        plant_id, _ = _prior_plant(db, now)
        deps = make_deps(
            chat_model=ScriptedStructuredModel(
                [
                    Roadmap(
                        steps=[
                            RoadmapStep(
                                ordinal=1,
                                action="Continue.",
                                rationale="Working.",
                                success_signal="No new symptoms.",
                                tier=IPMTier.CULTURAL,
                                day_offset=7,
                            )
                        ]
                    )
                ]
            )
        )
        state = _state(
            sample_images,
            plant_id,
            verdict=ProgressVerdict(verdict="improving", reasoning="Better."),
        )
        result = make_revise_roadmap(deps)(state)
        assert result["differential"].primary.disorder_id == "overwatering"

    def test_model_failure_still_carries_the_differential_forward(
        self, make_deps, sample_images, db, now
    ):
        """Better to keep the prior diagnosis visible than to lose it alongside a
        failed revision (same principle as build_roadmap's failure path)."""
        plant_id, _ = _prior_plant(db, now)
        deps = make_deps(chat_model=FailingChatModel(RuntimeError("api down")))
        state = _state(
            sample_images,
            plant_id,
            verdict=ProgressVerdict(verdict="static", reasoning="Unchanged."),
        )
        result = make_revise_roadmap(deps)(state)
        assert result["roadmap"] is None
        assert result["differential"].primary.disorder_id == "overwatering"
        assert result["errors"]
