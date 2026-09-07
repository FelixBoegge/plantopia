"""Tests for atomic persistence of a completed diagnosis."""

import pytest
from sqlalchemy import func, select

from agent.nodes.persist import make_persist
from agent.schemas import (
    Candidate,
    ContagionAssessment,
    Differential,
    IPMTier,
    Roadmap,
    RoadmapStep,
    Severity,
    SpeciesGuess,
)
from agent.state import DiagnosisState
from data.models import Diagnosis, Observation, Plant
from data.models import RoadmapStep as RoadmapStepRow


def _differential() -> Differential:
    return Differential(
        is_healthy=False,
        reasoning="Wet soil and yellowing.",
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
                probability=0.2,
                supporting_evidence=["wet soil"],
                contradicting_evidence=["stem firm"],
                distinguishing_test="Unpot the plant and inspect the roots.",
                severity=Severity.ACT_TODAY,
                transmissible=False,
            ),
        ],
    )


def _roadmap() -> Roadmap:
    return Roadmap(
        steps=[
            RoadmapStep(
                ordinal=1,
                action="Stop watering until the top 3 cm is dry.",
                rationale="Lets the roots breathe.",
                success_signal="No new yellow leaves.",
                tier=IPMTier.CULTURAL,
                day_offset=0,
            ),
            RoadmapStep(
                ordinal=2,
                action="Remove fully yellowed leaves.",
                rationale="Redirects resources.",
                success_signal="New growth at the crown.",
                tier=IPMTier.MECHANICAL,
                day_offset=7,
            ),
        ]
    )


def _state(images, **overrides) -> DiagnosisState:
    base = {
        "images": images,
        "plant_name": "Kitchen basil",
        "location_kind": "indoor",
        "species": SpeciesGuess(
            common_name="Basil", scientific_name="Ocimum basilicum", confidence=0.9
        ),
        "differential": _differential(),
        "contagion": ContagionAssessment(at_risk=False, advice="No spread risk."),
        "roadmap": _roadmap(),
    }
    return DiagnosisState(**{**base, **overrides})


def test_creates_a_plant_when_none_exists(make_deps, sample_images, db):
    deps = make_deps()
    result = make_persist(deps)(_state(sample_images))
    assert result["plant_id"] is not None
    row = db.get(Plant, result["plant_id"])
    assert row.name == "Kitchen basil"
    assert row.species == "Basil"


def test_reuses_an_existing_plant(owner, make_deps, sample_images, db, now):
    from data.repositories.plants import PlantRepository

    plant_id = PlantRepository(db).create(
        owner,
        name="Kitchen basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    deps = make_deps()
    result = make_persist(deps)(_state(sample_images, plant_id=plant_id))
    assert result["plant_id"] == plant_id
    assert db.scalar(select(func.count()).select_from(Plant)) == 1


def test_recheck_of_a_never_identified_plant_saves_the_new_species(
    owner, make_deps, sample_images, db, now
):
    from data.repositories.plants import PlantRepository

    plant_id = PlantRepository(db).create(
        owner,
        name="Mystery plant",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    deps = make_deps()
    make_persist(deps)(_state(sample_images, plant_id=plant_id))

    row = db.get(Plant, plant_id)
    assert row.species == "Basil"
    assert row.species_confidence == 0.9


def test_recheck_of_an_already_identified_plant_keeps_its_species(
    owner, make_deps, sample_images, db, now
):
    from data.repositories.plants import PlantRepository

    plant_id = PlantRepository(db).create(
        owner,
        name="Kitchen basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    deps = make_deps()
    make_persist(deps)(_state(sample_images, plant_id=plant_id))

    row = db.get(Plant, plant_id)
    assert row.species == "Basil"
    assert row.species_confidence == 0.9


def test_writes_an_observation_with_the_photo_refs(make_deps, sample_images, db):
    deps = make_deps()
    result = make_persist(deps)(_state(sample_images))
    row = db.get(Observation, result["observation_id"])
    assert row.kind == "initial"
    assert str(sample_images[0].ref) in row.photo_refs


def test_writes_the_diagnosis(make_deps, sample_images, db):
    deps = make_deps()
    result = make_persist(deps)(_state(sample_images))
    row = db.get(Diagnosis, result["diagnosis_id"])
    assert row.primary_candidate == "overwatering"


def test_writes_every_roadmap_step(make_deps, sample_images, db):
    deps = make_deps()
    make_persist(deps)(_state(sample_images))
    assert db.scalar(select(func.count()).select_from(RoadmapStepRow)) == 2


def test_a_healthy_diagnosis_persists_without_roadmap_steps(make_deps, sample_images, db):
    healthy = Differential(is_healthy=True, candidates=[], reasoning="Looks fine.")
    deps = make_deps()
    result = make_persist(deps)(_state(sample_images, differential=healthy, roadmap=None))
    assert result["diagnosis_id"] is not None
    assert db.scalar(select(func.count()).select_from(RoadmapStepRow)) == 0


def test_nothing_is_written_without_a_differential(make_deps, sample_images, db):
    deps = make_deps()
    result = make_persist(deps)(_state(sample_images, differential=None))
    assert result["diagnosis_id"] is None
    assert db.scalar(select(func.count()).select_from(Plant)) == 0


def test_a_failure_mid_write_leaves_no_partial_rows(make_deps, sample_images, db, monkeypatch):
    """The whole point of the transaction refactor."""
    from data.repositories.roadmap import RoadmapRepository

    def _explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(RoadmapRepository, "create_from_roadmap", _explode)

    deps = make_deps()
    with pytest.raises(RuntimeError, match="disk full"):
        make_persist(deps)(_state(sample_images))

    assert db.scalar(select(func.count()).select_from(Plant)) == 0
    assert db.scalar(select(func.count()).select_from(Observation)) == 0
    assert db.scalar(select(func.count()).select_from(Diagnosis)) == 0


def _state_ready_to_persist(sample_images):
    from agent.schemas import Candidate, Differential, Severity
    from agent.state import DiagnosisState

    return DiagnosisState(
        images=sample_images,
        plant_name="Test plant",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        differential=Differential(
            is_healthy=False,
            reasoning="Wet soil and lower-leaf yellowing.",
            candidates=[
                Candidate(
                    disorder_id="overwatering",
                    name="Overwatering",
                    probability=0.8,
                    supporting_evidence=["wet soil"],
                    contradicting_evidence=[],
                    distinguishing_test="Feel the soil three days after watering.",
                    severity=Severity.ACT_THIS_WEEK,
                    transmissible=False,
                ),
                Candidate(
                    disorder_id="root-rot",
                    name="Root rot",
                    probability=0.2,
                    supporting_evidence=["wet soil"],
                    contradicting_evidence=["stem firm"],
                    distinguishing_test="Unpot the plant and inspect the roots.",
                    severity=Severity.ACT_TODAY,
                    transmissible=False,
                ),
            ],
        ),
    )


def test_persist_writes_usage_from_the_collector(owner, make_deps, sample_images, db, now):
    """The collector is read inside persist's transaction, not by a second write."""
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    from agent.nodes.persist import make_persist
    from core.cost import UsageCollector
    from data.repositories.diagnoses import DiagnosisRepository

    collector = UsageCollector()
    collector.on_llm_end(
        LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content="x"))]],
            llm_output={
                "token_usage": {"prompt_tokens": 90, "completion_tokens": 10, "cost": 0.002}
            },
        )
    )

    deps = make_deps()
    state = _state_ready_to_persist(sample_images)
    config = {"configurable": {"thread_id": "t", "usage_collector": collector}}

    result = make_persist(deps)(state, config)

    record = DiagnosisRepository(db).get(owner, result["diagnosis_id"])
    assert record.token_usage == {
        "prompt_tokens": 90,
        "completion_tokens": 10,
        "total_tokens": 100,
    }
    assert record.cost_usd == 0.002


def test_persist_charges_the_diagnosis_for_the_pass_before_the_pause(
    owner, make_deps, sample_images, db
):
    """`U25`'s undercount, one layer up from the ledger.

    `persist` runs in the pass that *finishes* a run, and the vision and gate calls all
    happened before the clarifying-question pause. Reading the collector alone therefore
    wrote the finishing pass's spend to the record while `usage_events` — fixed in
    `cba92c0` — held the whole run. The two disagreed by the pre-interrupt spend, and it
    is the record's figure that `U23`'s cost badge would put on the screen.
    """
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    from agent.nodes.persist import make_persist
    from core.cost import UsageCollector, UsageSnapshot
    from data.repositories.diagnoses import DiagnosisRepository

    collector = UsageCollector()
    collector.on_llm_end(
        LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content="x"))]],
            llm_output={
                "token_usage": {"prompt_tokens": 90, "completion_tokens": 10, "cost": 0.002}
            },
        )
    )

    config = {
        "configurable": {
            "thread_id": "t",
            "usage_collector": collector,
            "carried_usage": UsageSnapshot(prompt_tokens=300, completion_tokens=40, cost_usd=0.005),
        }
    }

    result = make_persist(make_deps())(_state_ready_to_persist(sample_images), config)

    record = DiagnosisRepository(db).get(owner, result["diagnosis_id"])
    assert record.token_usage == {
        "prompt_tokens": 390,
        "completion_tokens": 50,
        "total_tokens": 440,
    }
    assert record.cost_usd == pytest.approx(0.007)


def test_persist_writes_null_usage_without_a_collector(owner, make_deps, sample_images, db):
    """Every existing caller and every unit test passes no collector. Must not crash."""
    from agent.nodes.persist import make_persist
    from data.repositories.diagnoses import DiagnosisRepository

    result = make_persist(make_deps())(_state_ready_to_persist(sample_images), None)

    record = DiagnosisRepository(db).get(owner, result["diagnosis_id"])
    assert record.token_usage is None
    assert record.cost_usd is None


class TestWhatThePlantEndsUpCalled:
    """Nobody is asked to name a plant they came here to have identified.

    The wizard used to require a name before the run started, which is the wrong way round:
    somebody arriving with a sick plant and no idea what it is had to invent something for a
    field, and "plant" is what they invented. It can be changed on the plant's own page
    afterwards, by which point they know what it is.
    """

    def test_what_the_owner_called_it_wins(self, make_deps, sample_images, db):
        deps = make_deps()

        make_persist(deps)(_state(sample_images, plant_name="Kitchen basil"), {})

        assert db.scalar(select(Plant.name)) == "Kitchen basil"

    def test_it_falls_back_to_what_the_plant_turned_out_to_be(self, make_deps, sample_images, db):
        deps = make_deps()

        make_persist(deps)(_state(sample_images, plant_name=None), {})

        assert db.scalar(select(Plant.name)) == "Basil"

    def test_a_blank_name_is_no_name(self, make_deps, sample_images, db):
        """A form sends an empty string for a field somebody left alone, and a plant called
        "" is a blank row in somebody's list."""
        deps = make_deps()

        make_persist(deps)(_state(sample_images, plant_name="   "), {})

        assert db.scalar(select(Plant.name)) == "Basil"

    def test_neither_named_nor_identified(self, make_deps, sample_images, db):
        """Deliberately plain: it appears in a list of somebody's plants, where "Unknown"
        reads as an error and this reads as a fact."""
        from agent.nodes.persist import UNNAMED

        deps = make_deps()

        make_persist(deps)(_state(sample_images, plant_name=None, species=None), {})

        assert db.scalar(select(Plant.name)) == UNNAMED
