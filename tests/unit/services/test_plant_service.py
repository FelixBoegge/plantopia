"""Tests for the plant-profile service backing My Plants and Plant detail."""

from services.plant_service import PlantDetail, PlantService, PlantSummary


def _service(db, now) -> PlantService:
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.feedback import FeedbackRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository

    return PlantService(
        plants=PlantRepository(db),
        observations=ObservationRepository(db),
        diagnoses=DiagnosisRepository(db),
        roadmap=RoadmapRepository(db),
        feedback=FeedbackRepository(db),
        now=now,
    )


def test_list_plants_is_empty_with_no_plants(db, now):
    assert _service(db, now).list_plants() == []


def test_list_plants_includes_the_latest_diagnosis_and_pending_count(db, now, sample_plant):
    summaries = _service(db, now).list_plants()
    assert len(summaries) == 1
    summary = summaries[0]
    assert isinstance(summary, PlantSummary)
    assert summary.plant.id == sample_plant
    assert summary.latest_diagnosis is not None
    assert summary.pending_step_count == 1  # sample_plant fixture marks one of two steps done


def test_get_plant_detail_returns_none_for_an_unknown_plant(db, now):
    assert _service(db, now).get_plant_detail(999_999) is None


def test_get_plant_detail_aggregates_the_timeline(db, now, sample_plant):
    detail = _service(db, now).get_plant_detail(sample_plant)
    assert isinstance(detail, PlantDetail)
    assert len(detail.observations) == 1
    assert len(detail.diagnoses) == 1
    assert len(detail.roadmap_steps) == 2


def test_feedback_is_due_once_a_step_is_done(db, now, sample_plant):
    """sample_plant already has one step marked done, so feedback should be due."""
    assert _service(db, now).get_plant_detail(sample_plant).feedback_due is True


def test_feedback_is_not_due_with_no_steps_done(db, now):
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
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    obs_id = ObservationRepository(db).create(
        plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    diagnosis_id = DiagnosisRepository(db).create(
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
    assert _service(db, now).get_plant_detail(plant_id).feedback_due is False


def test_feedback_is_not_due_when_only_an_older_diagnosis_has_a_done_step(db, now):
    """A done step on an OLDER diagnosis must not make feedback due for the latest one.

    Guards against a naive "any step anywhere is done" implementation that ignores
    which diagnosis a roadmap step belongs to.
    """
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

    def _differential() -> Differential:
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

    plant_id = PlantRepository(db).create(
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )

    # Older diagnosis, with its one roadmap step marked done.
    old_obs_id = ObservationRepository(db).create(
        plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    old_diagnosis_id = DiagnosisRepository(db).create(
        observation_id=old_obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="m",
        now=now(),
    )
    old_step_ids = RoadmapRepository(db).create_from_roadmap(
        diagnosis_id=old_diagnosis_id,
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
    RoadmapRepository(db).mark(old_step_ids[0], status="done", now=now())

    # Newer diagnosis, whose own roadmap step is still pending.
    new_obs_id = ObservationRepository(db).create(
        plant_id=plant_id, kind="recheck", photo_refs=[], user_notes=None, now=now()
    )
    new_diagnosis_id = DiagnosisRepository(db).create(
        observation_id=new_obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="m",
        now=now(),
    )
    RoadmapRepository(db).create_from_roadmap(
        diagnosis_id=new_diagnosis_id,
        plant_id=plant_id,
        roadmap=Roadmap(
            steps=[
                RoadmapStep(
                    ordinal=1,
                    action="Wait and observe again.",
                    rationale="Re-check after the last treatment.",
                    success_signal="No change in three days.",
                    tier=IPMTier.CULTURAL,
                    day_offset=0,
                )
            ]
        ),
        now=now(),
    )

    assert _service(db, now).get_plant_detail(plant_id).feedback_due is False


def test_feedback_is_not_due_once_already_given(db, now, sample_plant):
    service = _service(db, now)
    diagnosis_id = service.get_plant_detail(sample_plant).diagnoses[0].id
    service.submit_feedback(diagnosis_id=diagnosis_id, rating=5, did_it_help="yes", free_text=None)
    assert service.get_plant_detail(sample_plant).feedback_due is False


def test_mark_roadmap_step_persists(db, now, sample_plant):
    service = _service(db, now)
    step = service.get_plant_detail(sample_plant).roadmap_steps[-1]  # the still-pending one
    assert step.status == "pending"
    service.mark_roadmap_step(step.id, status="done")
    updated = next(
        s for s in service.get_plant_detail(sample_plant).roadmap_steps if s.id == step.id
    )
    assert updated.status == "done"
