"""Tests for the diagnosis repository, including JSON column round-tripping."""

from uuid import UUID

import pytest
from sqlalchemy import func, select

from agent.schemas import Candidate, ContagionAssessment, Differential, Passage, Severity
from data.models import Diagnosis
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository


def _create_minimal_diagnosis(repo, db, owner, now, **usage) -> UUID:
    """A plant, an observation, and one diagnosis. Returns the diagnosis id."""
    from agent.schemas import Candidate, Differential, Severity
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository

    plant_id = PlantRepository(db).create(
        owner,
        name="Test plant",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    observation_id = ObservationRepository(db).create(
        owner, plant_id=plant_id, kind="initial", photo_refs=["img-1"], user_notes=None, now=now()
    )
    differential = Differential(
        is_healthy=False,
        reasoning="Test reasoning.",
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
    )
    return repo.create(
        owner,
        observation_id=observation_id,
        plant_id=plant_id,
        differential=differential,
        contagion=None,
        retrieved=[],
        model="test-model",
        now=now(),
        **usage,
    )


@pytest.fixture
def ids(db, owner, now) -> tuple[UUID, UUID]:
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
        owner, plant_id=plant_id, kind="initial", photo_refs=["a"], user_notes=None, now=now()
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


def test_differential_round_trips_as_a_model(db, owner, now, ids):
    plant_id, obs_id = ids
    repo = DiagnosisRepository(db)
    diagnosis_id = repo.create(
        owner,
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="No quarantine needed."),
        retrieved=[Passage(doc_id="overwatering", section="Symptoms", text="...", score=0.8)],
        model="test-model",
        now=now(),
    )
    record = repo.get(owner, diagnosis_id)
    assert record is not None
    assert record.differential == _differential()
    assert record.differential.primary.disorder_id == "overwatering"


def test_denormalised_columns_are_populated(db, owner, now, ids):
    plant_id, obs_id = ids
    repo = DiagnosisRepository(db)
    diagnosis_id = repo.create(
        owner,
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    row = db.get(Diagnosis, diagnosis_id)
    assert row.primary_candidate == "overwatering"
    assert row.primary_confidence == 0.65
    assert row.severity == "act_this_week"


def test_healthy_diagnosis_has_null_primary(db, owner, now, ids):
    plant_id, obs_id = ids
    repo = DiagnosisRepository(db)
    diagnosis_id = repo.create(
        owner,
        observation_id=obs_id,
        plant_id=plant_id,
        differential=Differential(is_healthy=True, candidates=[], reasoning="Looks healthy."),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    assert db.get(Diagnosis, diagnosis_id).primary_candidate is None
    assert repo.get(owner, diagnosis_id).differential.is_healthy is True


def test_retrieved_passages_round_trip(db, owner, now, ids):
    plant_id, obs_id = ids
    passages = [
        Passage(doc_id="root-rot", section="Symptoms", text="brown mushy roots", score=0.9),
        Passage(doc_id="overwatering", section="Look-alikes", text="see root rot", score=0.4),
    ]
    repo = DiagnosisRepository(db)
    diagnosis_id = repo.create(
        owner,
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=passages,
        model="test-model",
        now=now(),
    )
    assert repo.get(owner, diagnosis_id).retrieved == passages


def test_latest_for_plant_returns_the_newest(db, owner, now, ids):
    plant_id, obs_id = ids
    repo = DiagnosisRepository(db)
    repo.create(
        owner,
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    newest = repo.create(
        owner,
        observation_id=obs_id,
        plant_id=plant_id,
        differential=Differential(is_healthy=True, candidates=[], reasoning="Recovered."),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    assert repo.latest_for_plant(owner, plant_id).id == newest


def test_latest_for_plant_returns_none_when_no_diagnoses(db, owner, now, ids):
    plant_id, _ = ids
    assert DiagnosisRepository(db).latest_for_plant(owner, plant_id) is None


def test_deleting_a_plant_cascades_to_diagnoses(db, owner, now, ids):
    plant_id, obs_id = ids
    DiagnosisRepository(db).create(
        owner,
        observation_id=obs_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    PlantRepository(db).delete(owner, plant_id)
    db.flush()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Diagnosis)) == 0


def test_list_for_plant_returns_every_diagnosis_newest_first(db, owner, now):
    from datetime import timedelta

    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository

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
    repo = DiagnosisRepository(db)
    ids = []
    for i in range(3):
        obs_id = ObservationRepository(db).create(
            owner, plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
        )
        ids.append(
            repo.create(
                owner,
                observation_id=obs_id,
                plant_id=plant_id,
                differential=_differential(),
                contagion=None,
                retrieved=[],
                model="test-model",
                now=now() + timedelta(days=i),
            )
        )

    result = [d.id for d in repo.list_for_plant(owner, plant_id)]
    assert result == list(reversed(ids))


def test_list_for_plant_is_empty_for_a_plant_with_no_diagnoses(db, owner, now):
    from data.repositories.plants import PlantRepository

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
    assert DiagnosisRepository(db).list_for_plant(owner, plant_id) == []


def test_token_usage_round_trips(db, owner, now):
    """M12: these columns exist and create() already accepts them — nothing wrote them."""
    from data.repositories.diagnoses import DiagnosisRepository

    repo = DiagnosisRepository(db)
    diagnosis_id = _create_minimal_diagnosis(
        repo,
        db,
        owner,
        now,
        token_usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        cost_usd=0.0042,
    )

    record = repo.get(owner, diagnosis_id)
    assert record.token_usage == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    }
    assert record.cost_usd == 0.0042


def test_token_usage_is_none_when_not_written(db, owner, now):
    from data.repositories.diagnoses import DiagnosisRepository

    repo = DiagnosisRepository(db)
    diagnosis_id = _create_minimal_diagnosis(repo, db, owner, now)

    record = repo.get(owner, diagnosis_id)
    assert record.token_usage is None
    assert record.cost_usd is None


class TestTheSpeciesProvenance:
    """Which method produced the species, and whether a person agreed to it.

    Two columns whose only purpose is telling apart the two ways a diagnosis can be wrong:
    bad reasoning about the right plant, or good reasoning about the wrong one. They look
    identical afterwards without this.
    """

    @pytest.mark.parametrize(
        ("method", "confirmed"),
        [
            ("vision", False),
            ("vision", True),
            ("plantnet", True),
            ("agreed", False),
            ("typed", True),
            (None, False),
        ],
        ids=[
            "vision-unconfirmed",
            "vision-confirmed",
            "plantnet-confirmed",
            "agreed-unconfirmed",
            "typed-confirmed",
            "unknown-unconfirmed",
        ],
    )
    def test_it_round_trips(self, db, owner, now, method, confirmed):
        repo = DiagnosisRepository(db)

        diagnosis_id = _create_minimal_diagnosis(
            repo, db, owner, now, species_method=method, species_confirmed=confirmed
        )

        record = repo.get(owner, diagnosis_id)
        assert record.species_method == method
        assert record.species_confirmed is confirmed

    def test_a_diagnosis_written_without_it_reads_as_unknown(self, db, owner, now):
        """Every row that existed before these columns did. Null means unknown, and a
        backfill would have had to invent a provenance for exactly the field whose job is
        being trustworthy about provenance."""
        repo = DiagnosisRepository(db)

        diagnosis_id = _create_minimal_diagnosis(repo, db, owner, now)

        record = repo.get(owner, diagnosis_id)
        assert record.species_method is None
        assert record.species_confirmed is False

    def test_an_existing_row_can_be_read_after_the_migration(self, db, owner, now):
        """The column is NOT NULL with a server default, so a row inserted without it —
        which is what every pre-migration row is — still reads."""
        from sqlalchemy import text

        repo = DiagnosisRepository(db)
        diagnosis_id = _create_minimal_diagnosis(repo, db, owner, now)
        db.execute(
            text("UPDATE diagnoses SET species_method = NULL WHERE id = :id"),
            {"id": diagnosis_id},
        )

        record = repo.get(owner, diagnosis_id)
        assert record.species_method is None
