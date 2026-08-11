"""Control-flow tests for the re-check path through the diagnosis graph.

Companion to tests/graph/test_diagnosis_graph.py, which covers the first-time path.
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from agent.diagnosis_graph import build_diagnosis_graph
from agent.schemas import (
    Candidate,
    Differential,
    ImageQuality,
    IPMTier,
    PlantCheck,
    ProgressVerdict,
    Roadmap,
    RoadmapStep,
    Severity,
    Symptom,
    SymptomPosition,
    SymptomSet,
)
from agent.state import DiagnosisState
from tests.fakes.chat_models import ScriptedStructuredModel


@pytest.fixture
def config():
    return {"configurable": {"thread_id": "recheck-thread"}}


def _symptoms() -> SymptomSet:
    return SymptomSet(
        symptoms=[
            Symptom(
                description="Fewer yellow leaves",
                position=SymptomPosition.LOWER_LEAVES,
                severity=Severity.MONITOR,
            )
        ],
        soil_condition="drier",
        overall_vigor="good",
    )


def _state(images, plant_id) -> DiagnosisState:
    return DiagnosisState(
        images=images, plant_name="Kitchen basil", location_kind="indoor", plant_id=plant_id
    )


def _intake(gate=None):
    return gate or ScriptedStructuredModel(
        [
            PlantCheck(is_plant=True, what_it_is="a basil plant"),
            ImageQuality(usable=True, problem=None, guidance=None),
        ]
    )


class TestRecheckRouting:
    def test_a_known_plant_skips_identification(
        self, make_deps, sample_images, sample_plant, config
    ):
        """Only one vision call is scripted (for assess_symptoms). If routing wrongly
        visited identify_plant first, assess_symptoms would find the script
        exhausted and raise — this is the same technique
        TestOrdering.test_species_is_identified_before_symptoms_are_assessed uses in
        tests/graph/test_diagnosis_graph.py."""
        vision = ScriptedStructuredModel([_symptoms()])
        chat = ScriptedStructuredModel(
            [ProgressVerdict(verdict="improving", reasoning="Fewer symptoms.")]
        )
        deps = make_deps(
            gate_model=_intake(),
            vision_model=vision,
            chat_model=chat,
            care_profile=lambda species: None,
        )
        graph = build_diagnosis_graph(deps, MemorySaver())

        result = graph.invoke(_state(sample_images, sample_plant), config)

        assert result["symptoms"] is not None
        assert vision.call_count == 1

    def test_a_recheck_never_interrupts(self, make_deps, sample_images, sample_plant, config):
        vision = ScriptedStructuredModel([_symptoms()])
        chat = ScriptedStructuredModel([ProgressVerdict(verdict="static", reasoning="Unchanged.")])
        deps = make_deps(gate_model=_intake(), vision_model=vision, chat_model=chat)
        graph = build_diagnosis_graph(deps, MemorySaver())

        result = graph.invoke(_state(sample_images, sample_plant), config)
        assert "__interrupt__" not in result


class TestImprovingAndStatic:
    def test_improving_revises_the_roadmap_without_rediagnosing(
        self, make_deps, sample_images, sample_plant, config, db
    ):
        vision = ScriptedStructuredModel([_symptoms()])
        chat = ScriptedStructuredModel(
            [
                ProgressVerdict(verdict="improving", reasoning="Fewer yellow leaves than before."),
                Roadmap(
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
                ),
            ]
        )
        deps = make_deps(gate_model=_intake(), vision_model=vision, chat_model=chat)
        graph = build_diagnosis_graph(deps, MemorySaver())

        result = graph.invoke(_state(sample_images, sample_plant), config)

        assert result["differential"].primary.disorder_id == "overwatering"  # carried forward
        assert result["roadmap"].steps[0].action == "Continue the current watering schedule."
        assert result["diagnosis_id"] is not None
        kind = db.execute("SELECT kind FROM observations ORDER BY id DESC LIMIT 1").fetchone()[
            "kind"
        ]
        assert kind == "recheck"


class TestWorseningAndNewProblem:
    def test_worsening_triggers_a_full_rediagnosis(
        self, make_deps, sample_images, sample_plant, config
    ):
        vision = ScriptedStructuredModel([_symptoms()])
        new_differential = Differential(
            is_healthy=False,
            reasoning="Roots are affected, not just watering habits.",
            candidates=[
                Candidate(
                    disorder_id="root-rot",
                    name="Root rot",
                    probability=0.8,
                    supporting_evidence=["mushy roots"],
                    contradicting_evidence=[],
                    distinguishing_test="Unpot and check for brown, mushy roots.",
                    severity=Severity.ACT_TODAY,
                    transmissible=False,
                ),
                Candidate(
                    disorder_id="overwatering",
                    name="Overwatering",
                    probability=0.2,
                    supporting_evidence=["wet soil"],
                    contradicting_evidence=[],
                    distinguishing_test="Feel the soil three days after watering.",
                    severity=Severity.ACT_THIS_WEEK,
                    transmissible=False,
                ),
            ],
        )
        chat = ScriptedStructuredModel(
            [
                ProgressVerdict(
                    verdict="worsening", reasoning="Symptoms progressed despite compliance."
                ),
                new_differential,
                Roadmap(
                    steps=[
                        RoadmapStep(
                            ordinal=1,
                            action="Unpot and trim any mushy roots.",
                            rationale="Root rot keeps spreading otherwise.",
                            success_signal="Remaining roots are firm and white.",
                            tier=IPMTier.MECHANICAL,
                            day_offset=0,
                        )
                    ]
                ),
            ]
        )
        deps = make_deps(gate_model=_intake(), vision_model=vision, chat_model=chat)
        graph = build_diagnosis_graph(deps, MemorySaver())

        result = graph.invoke(_state(sample_images, sample_plant), config)

        assert result["differential"].primary.disorder_id == "root-rot"  # genuinely re-diagnosed
        assert result["roadmap"].steps[0].action == "Unpot and trim any mushy roots."
