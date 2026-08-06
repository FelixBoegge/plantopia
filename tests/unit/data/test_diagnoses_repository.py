"""Tests for the diagnosis repository, including JSON column round-tripping."""

import pytest

from agent.schemas import Candidate, ContagionAssessment, Differential, Passage, Severity
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository


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
        plant_id=plant_id, kind="initial", photo_refs=["a"], user_notes=None, now=now()
    )
    return plant_id, obs_id


def _differential() -> Differential:
    return Differential(
        is_healthy=False,
        reasoning="Wet soil plus lower-leaf yellowing points to overwatering.",
        candidates=[
            Candidate(
                disorder_id="overwatering",
                name="Overwatering",
                probability=0.65,
                supporting_evidence=["soil wet", "lower leaves yellow"],
                contradicting_evidence=["no smell from the soil"],
                distinguishing_test=(
                    "Check whether the soil is still wet three days after watering."
                ),
                severity=Severity.ACT_THIS_WEEK,
                transmissible=False,
            ),
            Candidate(
                disorder_id="root-rot",
                name="Root rot",
                probability=0.25,
                supporting_evidence=["soil wet"],
                contradicting_evidence=["stem still firm"],
                distinguishing_test=(
                    "Slide the plant out of its pot and look for brown mushy roots."
                ),
                severity=Severity.ACT_TODAY,
                transmissible=False,
            ),
        ],
    )


def test_differential_round_trips_as_a_model(db, now, ids):
    plant_id, obs_id = ids
    repo = DiagnosisRepository(db)
    diagnosis_id = repo.create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="No quarantine needed."),
        retrieved=[Passage(doc_id="overwatering", section="Symptoms", text="...", score=0.8)],
        model="test-model",
        now=now(),
    )
    record = repo.get(diagnosis_id)
    assert record is not None
    assert record.differential == _differential()
    assert record.differential.primary.disorder_id == "overwatering"


def test_denormalised_columns_are_populated(db, now, ids):
    plant_id, obs_id = ids
    repo = DiagnosisRepository(db)
    diagnosis_id = repo.create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    row = db.execute("SELECT * FROM diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
    assert row["primary_candidate"] == "overwatering"
    assert row["primary_confidence"] == 0.65
    assert row["severity"] == "act_this_week"


def test_healthy_diagnosis_has_null_primary(db, now, ids):
    plant_id, obs_id = ids
    repo = DiagnosisRepository(db)
    diagnosis_id = repo.create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=Differential(is_healthy=True, candidates=[], reasoning="Looks healthy."),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    row = db.execute("SELECT * FROM diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
    assert row["primary_candidate"] is None
    assert repo.get(diagnosis_id).differential.is_healthy is True


def test_retrieved_passages_round_trip(db, now, ids):
    plant_id, obs_id = ids
    passages = [
        Passage(doc_id="root-rot", section="Symptoms", text="brown mushy roots", score=0.9),
        Passage(doc_id="overwatering", section="Look-alikes", text="see root rot", score=0.4),
    ]
    repo = DiagnosisRepository(db)
    diagnosis_id = repo.create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=passages,
        model="test-model",
        now=now(),
    )
    assert repo.get(diagnosis_id).retrieved == passages


def test_latest_for_plant_returns_the_newest(db, now, ids):
    plant_id, obs_id = ids
    repo = DiagnosisRepository(db)
    repo.create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    newest = repo.create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=Differential(is_healthy=True, candidates=[], reasoning="Recovered."),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    assert repo.latest_for_plant(plant_id).id == newest


def test_latest_for_plant_returns_none_when_no_diagnoses(db, now, ids):
    plant_id, _ = ids
    assert DiagnosisRepository(db).latest_for_plant(plant_id) is None


def test_deleting_a_plant_cascades_to_diagnoses(db, now, ids):
    plant_id, obs_id = ids
    DiagnosisRepository(db).create(
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    PlantRepository(db).delete(plant_id)
    assert db.execute("SELECT COUNT(*) AS n FROM diagnoses").fetchone()["n"] == 0
