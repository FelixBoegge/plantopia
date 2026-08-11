"""Tests for roadmap step persistence and status transitions."""

from datetime import UTC, datetime, timedelta

import pytest

from agent.schemas import IPMTier, Roadmap, RoadmapStep
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.roadmap import RoadmapRepository
from tests.unit.data.test_diagnoses_repository import _differential


@pytest.fixture
def ids(db, now) -> tuple[int, int]:
    plant_id = PlantRepository(db).create(
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    obs_id = ObservationRepository(db).create(
        plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    from agent.schemas import ContagionAssessment

    diagnosis_id = DiagnosisRepository(db).create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    return plant_id, diagnosis_id


def _roadmap() -> Roadmap:
    return Roadmap(
        steps=[
            RoadmapStep(
                ordinal=1,
                action="Stop watering until the top 3 cm of soil is dry.",
                rationale="Removes the anaerobic conditions the pathogen needs.",
                success_signal="No new yellow leaves after seven days.",
                tier=IPMTier.CULTURAL,
                day_offset=0,
            ),
            RoadmapStep(
                ordinal=2,
                action="Remove any leaves that have yellowed completely.",
                rationale="Redirects the plant's resources to healthy tissue.",
                success_signal="New growth appears at the crown.",
                tier=IPMTier.MECHANICAL,
                day_offset=7,
            ),
        ]
    )


def test_create_from_roadmap_computes_absolute_due_dates(db, now, ids):
    plant_id, diagnosis_id = ids
    repo = RoadmapRepository(db)
    repo.create_from_roadmap(
        diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=now()
    )
    steps = repo.list_for_plant(plant_id)
    assert steps[0].due_date == now()
    assert steps[1].due_date == now() + timedelta(days=7)


def test_create_from_roadmap_returns_one_id_per_step(db, now, ids):
    plant_id, diagnosis_id = ids
    ids_created = RoadmapRepository(db).create_from_roadmap(
        diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=now()
    )
    assert len(ids_created) == 2


def test_steps_start_pending(db, now, ids):
    plant_id, diagnosis_id = ids
    repo = RoadmapRepository(db)
    repo.create_from_roadmap(
        diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=now()
    )
    assert all(s.status == "pending" for s in repo.list_for_plant(plant_id))
    assert all(s.completed_at is None for s in repo.list_for_plant(plant_id))


def test_mark_done_records_completion_time(db, now, ids):
    plant_id, diagnosis_id = ids
    repo = RoadmapRepository(db)
    step_ids = repo.create_from_roadmap(
        diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=now()
    )
    completion = now() + timedelta(days=1)
    repo.mark(step_ids[0], status="done", now=completion)

    step = next(s for s in repo.list_for_plant(plant_id) if s.id == step_ids[0])
    assert step.status == "done"
    assert step.completed_at == completion


def test_mark_skipped_records_completion_time(db, now, ids):
    plant_id, diagnosis_id = ids
    repo = RoadmapRepository(db)
    step_ids = repo.create_from_roadmap(
        diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=now()
    )
    repo.mark(step_ids[1], status="skipped", now=now())
    step = next(s for s in repo.list_for_plant(plant_id) if s.id == step_ids[1])
    assert step.status == "skipped"


def test_mark_rejects_an_unknown_status(db, now, ids):
    plant_id, diagnosis_id = ids
    repo = RoadmapRepository(db)
    step_ids = repo.create_from_roadmap(
        diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=now()
    )
    with pytest.raises(ValueError, match="status"):
        repo.mark(step_ids[0], status="finished", now=now())  # type: ignore[arg-type]


def test_due_before_returns_only_pending_overdue_steps(db, now, ids):
    plant_id, diagnosis_id = ids
    repo = RoadmapRepository(db)
    step_ids = repo.create_from_roadmap(
        diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=now()
    )
    cutoff = now() + timedelta(days=1)

    assert [s.id for s in repo.due_before(cutoff)] == [step_ids[0]]

    repo.mark(step_ids[0], status="done", now=now())
    assert repo.due_before(cutoff) == []


def test_due_dates_survive_a_month_boundary(db, ids):
    plant_id, diagnosis_id = ids
    repo = RoadmapRepository(db)
    late_january = datetime(2026, 1, 28, 9, 0, tzinfo=UTC)
    repo.create_from_roadmap(
        diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=late_january
    )
    steps = repo.list_for_plant(plant_id)
    assert steps[1].due_date == datetime(2026, 2, 4, 9, 0, tzinfo=UTC)


def test_mark_raises_on_an_unknown_step_id(db, now, ids):
    plant_id, diagnosis_id = ids
    repo = RoadmapRepository(db)
    repo.create_from_roadmap(
        diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=now()
    )

    with pytest.raises(ValueError, match="no roadmap step"):
        repo.mark(999_999, status="done", now=now())


def test_connection_property_exposes_the_underlying_connection(db):
    repo = RoadmapRepository(db)
    assert repo.connection is db
