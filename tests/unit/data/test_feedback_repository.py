"""Tests for treatment-outcome feedback persistence."""

from uuid import UUID

import pytest

from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.feedback import FeedbackRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from tests.unit.data.test_diagnoses_repository import _differential


@pytest.fixture
def diagnosis_id(db, owner, now) -> UUID:
    plant_id = PlantRepository(db).create(
        owner,
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    obs_id = ObservationRepository(db).create(
        owner, plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    return DiagnosisRepository(db).create(
        owner,
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=None,
        retrieved=[],
        model="test-model",
        now=now(),
    )


def test_create_and_read_roundtrip(db, owner, now, diagnosis_id):
    repo = FeedbackRepository(db)
    feedback_id = repo.create(
        owner,
        diagnosis_id=diagnosis_id,
        rating=4,
        did_it_help="yes",
        free_text="The soil dried out and new growth appeared.",
        now=now(),
    )
    assert isinstance(feedback_id, UUID)


def test_exists_for_diagnosis_is_false_before_any_feedback(db, owner, diagnosis_id):
    assert FeedbackRepository(db).exists_for_diagnosis(owner, diagnosis_id) is False


def test_exists_for_diagnosis_is_true_after_create(db, owner, now, diagnosis_id):
    repo = FeedbackRepository(db)
    repo.create(
        owner,
        diagnosis_id=diagnosis_id,
        rating=None,
        did_it_help="too_early",
        free_text=None,
        now=now(),
    )
    assert repo.exists_for_diagnosis(owner, diagnosis_id) is True


def test_session_property_exposes_the_underlying_session(db, owner):
    assert FeedbackRepository(db).session is db
