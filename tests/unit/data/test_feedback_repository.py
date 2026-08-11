"""Tests for treatment-outcome feedback persistence."""

import pytest

from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.feedback import FeedbackRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from tests.unit.data.test_diagnoses_repository import _differential


@pytest.fixture
def diagnosis_id(db, now) -> int:
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
    return DiagnosisRepository(db).create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=None,
        retrieved=[],
        model="test-model",
        now=now(),
    )


def test_create_and_read_roundtrip(db, now, diagnosis_id):
    repo = FeedbackRepository(db)
    feedback_id = repo.create(
        diagnosis_id=diagnosis_id,
        rating=4,
        did_it_help="yes",
        free_text="The soil dried out and new growth appeared.",
        now=now(),
    )
    assert isinstance(feedback_id, int)


def test_exists_for_diagnosis_is_false_before_any_feedback(db, diagnosis_id):
    assert FeedbackRepository(db).exists_for_diagnosis(diagnosis_id) is False


def test_exists_for_diagnosis_is_true_after_create(db, now, diagnosis_id):
    repo = FeedbackRepository(db)
    repo.create(
        diagnosis_id=diagnosis_id, rating=None, did_it_help="too_early", free_text=None, now=now()
    )
    assert repo.exists_for_diagnosis(diagnosis_id) is True


def test_connection_property_exposes_the_underlying_connection(db):
    assert FeedbackRepository(db).connection is db
