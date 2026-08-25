"""Tests for the plant-profile service backing My Plants and Plant detail."""

from uuid import UUID

from core.ids import new_id
from services.plant_service import PlantDetail, PlantService, PlantSummary


def _service(owner, db, now) -> PlantService:
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.feedback import FeedbackRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository

    return PlantService(
        user_id=owner,
        plants=PlantRepository(db),
        observations=ObservationRepository(db),
        diagnoses=DiagnosisRepository(db),
        roadmap=RoadmapRepository(db),
        feedback=FeedbackRepository(db),
        now=now,
    )


def test_list_plants_is_empty_with_no_plants(owner, db, now):
    assert _service(owner, db, now).list_plants() == []


def test_list_plants_includes_the_latest_diagnosis_and_pending_count(owner, db, now, sample_plant):
    summaries = _service(owner, db, now).list_plants()
    assert len(summaries) == 1
    summary = summaries[0]
    assert isinstance(summary, PlantSummary)
    assert summary.plant.id == sample_plant
    assert summary.latest_diagnosis is not None
    assert summary.pending_step_count == 1  # sample_plant fixture marks one of two steps done


def test_get_plant_detail_returns_none_for_an_unknown_plant(owner, db, now):
    assert _service(owner, db, now).get_plant_detail(new_id()) is None


def test_get_plant_detail_aggregates_the_timeline(owner, db, now, sample_plant):
    detail = _service(owner, db, now).get_plant_detail(sample_plant)
    assert isinstance(detail, PlantDetail)
    assert len(detail.observations) == 1
    assert len(detail.diagnoses) == 1
    assert len(detail.roadmap_steps) == 2


def test_feedback_is_due_once_a_step_is_done(owner, db, now, sample_plant):
    """sample_plant already has one step marked done, so feedback should be due."""
    assert _service(owner, db, now).get_plant_detail(sample_plant).feedback_due is True


def test_feedback_is_not_due_with_no_steps_done(owner, db, now):
    from agent.schemas import (
        Candidate,
        ContagionAssessment,
        Differential,
        IPMTier,
        Roadmap,
        RoadmapStep,
        Severity,
    )
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository

    plant_id = PlantRepository(db).create(
        owner,
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    obs_id = ObservationRepository(db).create(
        owner, plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    diagnosis_id = DiagnosisRepository(db).create(
        owner,
        observation_id=obs_id,
        plant_id=plant_id,
        differential=Differential(
            is_healthy=False,
            reasoning="r",
            candidates=[
                Candidate(
                    disorder_id="d",
                    name="D",
                    probability=0.6,
                    supporting_evidence=["e"],
                    contradicting_evidence=[],
                    distinguishing_test="Do the fifteen-character test.",
                    severity=Severity.MONITOR,
                    transmissible=False,
                ),
                Candidate(
                    disorder_id="d2",
                    name="D2",
                    probability=0.4,
                    supporting_evidence=["e"],
                    contradicting_evidence=[],
                    distinguishing_test="Do another fifteen-char test.",
                    severity=Severity.MONITOR,
                    transmissible=False,
                ),
            ],
        ),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="m",
        now=now(),
    )
    RoadmapRepository(db).create_from_roadmap(
        owner,
        diagnosis_id=diagnosis_id,
        plant_id=plant_id,
        roadmap=Roadmap(
            steps=[
                RoadmapStep(
                    ordinal=1,
                    action="Wait and observe.",
                    rationale="It just started.",
                    success_signal="No change in three days.",
                    tier=IPMTier.CULTURAL,
                    day_offset=0,
                )
            ]
        ),
        now=now(),
    )
    assert _service(owner, db, now).get_plant_detail(plant_id).feedback_due is False


def _differential():
    from agent.schemas import Candidate, Differential, Severity

    return Differential(
        is_healthy=False,
        reasoning="r",
        candidates=[
            Candidate(
                disorder_id="d",
                name="D",
                probability=0.6,
                supporting_evidence=["e"],
                contradicting_evidence=[],
                distinguishing_test="Do the fifteen-character test.",
                severity=Severity.MONITOR,
                transmissible=False,
            ),
            Candidate(
                disorder_id="d2",
                name="D2",
                probability=0.4,
                supporting_evidence=["e"],
                contradicting_evidence=[],
                distinguishing_test="Do another fifteen-char test.",
                severity=Severity.MONITOR,
                transmissible=False,
            ),
        ],
    )


def _rechecked_plant(owner, db, now) -> tuple[UUID, list[UUID], list[UUID]]:
    """A plant that has been through one diagnosis and then one re-check.

    Every re-check writes a new ``diagnoses`` row and a whole new roadmap (design
    decision P2-4), so this is the ordinary post-re-check shape rather than an edge
    case. The older plan has two steps (one ticked, one abandoned still-pending); the
    current plan has one, still pending.

    Returns ``(plant_id, old_step_ids, new_step_ids)``.
    """
    from agent.schemas import ContagionAssessment, IPMTier, Roadmap, RoadmapStep
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository

    plant_id = PlantRepository(db).create(
        owner,
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )

    def _diagnose(kind: str) -> UUID:
        observation_id = ObservationRepository(db).create(
            owner, plant_id=plant_id, kind=kind, photo_refs=[], user_notes=None, now=now()
        )
        return DiagnosisRepository(db).create(
            owner,
            observation_id=observation_id,
            plant_id=plant_id,
            differential=_differential(),
            contagion=ContagionAssessment(at_risk=False, advice="none"),
            retrieved=[],
            model="m",
            now=now(),
        )

    def _step(ordinal: int, action: str) -> RoadmapStep:
        return RoadmapStep(
            ordinal=ordinal,
            action=action,
            rationale="Re-check after the last treatment.",
            success_signal="No change in three days.",
            tier=IPMTier.CULTURAL,
            day_offset=0,
        )

    old_diagnosis_id = _diagnose("initial")
    old_step_ids = RoadmapRepository(db).create_from_roadmap(
        owner,
        diagnosis_id=old_diagnosis_id,
        plant_id=plant_id,
        roadmap=Roadmap(
            steps=[_step(1, "Wait and observe."), _step(2, "Move it into more light.")]
        ),
        now=now(),
    )
    RoadmapRepository(db).mark(owner, old_step_ids[0], status="done", now=now())

    new_diagnosis_id = _diagnose("recheck")
    new_step_ids = RoadmapRepository(db).create_from_roadmap(
        owner,
        diagnosis_id=new_diagnosis_id,
        plant_id=plant_id,
        roadmap=Roadmap(steps=[_step(1, "Wait and observe again.")]),
        now=now(),
    )
    return plant_id, old_step_ids, new_step_ids


def test_feedback_is_not_due_when_only_an_older_diagnosis_has_a_done_step(owner, db, now):
    """A done step on an OLDER diagnosis must not make feedback due for the latest one.

    Guards against a naive "any step anywhere is done" implementation that ignores
    which diagnosis a roadmap step belongs to.
    """
    plant_id, _, _ = _rechecked_plant(owner, db, now)
    assert _service(owner, db, now).get_plant_detail(plant_id).feedback_due is False


def test_the_checklist_shows_only_the_latest_diagnosis_steps(owner, db, now):
    """Every re-check writes a whole new roadmap (P2-4). Feeding the checklist every
    step ever created for the plant left superseded plans mixed in with the current
    one, all still tickable — so the owner could tick a step from a plan that had
    already been replaced, and the list only ever grew."""
    plant_id, old_step_ids, new_step_ids = _rechecked_plant(owner, db, now)

    steps = _service(owner, db, now).get_plant_detail(plant_id).roadmap_steps

    assert [s.id for s in steps] == new_step_ids
    assert not set(old_step_ids) & {s.id for s in steps}


def test_the_pending_count_reflects_only_the_latest_diagnosis(owner, db, now):
    """The My Plants badge counted pending steps across every diagnosis ever, so it
    climbed monotonically with each re-check. Here the superseded plan leaves one
    pending step behind and the current plan has one: the badge must read 1, not 2."""
    plant_id, _, _ = _rechecked_plant(owner, db, now)

    summary = next(s for s in _service(owner, db, now).list_plants() if s.plant.id == plant_id)

    assert summary.pending_step_count == 1


def test_a_plant_with_no_diagnoses_has_no_steps_and_no_pending_count(owner, db, now):
    """The latest-diagnosis filter must degrade to "nothing", not raise, for a plant
    that has never been diagnosed."""
    from data.repositories.plants import PlantRepository

    plant_id = PlantRepository(db).create(
        owner,
        name="Brand new",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    service = _service(owner, db, now)

    assert service.get_plant_detail(plant_id).roadmap_steps == []
    summary = next(s for s in service.list_plants() if s.plant.id == plant_id)
    assert summary.pending_step_count == 0


def test_feedback_is_not_due_once_already_given(owner, db, now, sample_plant):
    service = _service(owner, db, now)
    diagnosis_id = service.get_plant_detail(sample_plant).diagnoses[0].id
    service.submit_feedback(diagnosis_id=diagnosis_id, rating=5, did_it_help="yes", free_text=None)
    assert service.get_plant_detail(sample_plant).feedback_due is False


def test_mark_roadmap_step_persists(owner, db, now, sample_plant):
    service = _service(owner, db, now)
    step = service.get_plant_detail(sample_plant).roadmap_steps[-1]  # the still-pending one
    assert step.status == "pending"
    service.mark_roadmap_step(step.id, status="done")
    updated = next(
        s for s in service.get_plant_detail(sample_plant).roadmap_steps if s.id == step.id
    )
    assert updated.status == "done"


def test_rename_plant_persists(owner, db, now, sample_plant):
    """The name confirmed after identification replaces the placeholder from intake."""
    service = _service(owner, db, now)
    service.rename_plant(sample_plant, name="Kitchen basil")
    assert service.get_plant_detail(sample_plant).plant.name == "Kitchen basil"


def test_rename_plant_trims_surrounding_whitespace(owner, db, now, sample_plant):
    service = _service(owner, db, now)
    service.rename_plant(sample_plant, name="  Kitchen basil  ")
    assert service.get_plant_detail(sample_plant).plant.name == "Kitchen basil"


def test_rename_plant_refuses_a_blank_name(owner, db, now, sample_plant):
    """A nameless plant renders as an unlabelled card with no way back to fix it, so
    the emptiness is refused here rather than stored and worked around in the UI."""
    import pytest

    service = _service(owner, db, now)
    before = service.get_plant_detail(sample_plant).plant.name

    with pytest.raises(ValueError):
        service.rename_plant(sample_plant, name="   ")

    assert service.get_plant_detail(sample_plant).plant.name == before


def test_rename_plant_leaves_the_species_alone(owner, db, now, sample_plant):
    """The name is what the owner calls it; the species is what it is. Confirming one
    must not overwrite the other."""
    service = _service(owner, db, now)
    species = service.get_plant_detail(sample_plant).plant.species

    service.rename_plant(sample_plant, name="Kitchen basil")

    assert service.get_plant_detail(sample_plant).plant.species == species
