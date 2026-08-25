"""Fixtures for the endpoint tier.

The app is built per test with its dependencies overridden onto the test session, so a
request runs against the same rolled-back transaction every other test uses. Nothing here
reaches a model: the one endpoint that would — sending a chat message — is given the
scripted fake the rest of the suite uses.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from agent.schemas import (
    Candidate,
    ContagionAssessment,
    Differential,
    IPMTier,
    Roadmap,
    RoadmapStep,
    Severity,
)
from api import dependencies
from api.main import create_app
from core.blobs import PostgresBlobStore
from core.config import Settings
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.feedback import FeedbackRepository
from data.repositories.messages import MessageRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.roadmap import RoadmapRepository
from services.plant_service import PlantService

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


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
                distinguishing_test="Push a finger into the soil three days after watering.",
                severity=Severity.ACT_THIS_WEEK,
                transmissible=False,
            ),
            Candidate(
                disorder_id="root-rot",
                name="Root rot",
                probability=0.3,
                supporting_evidence=["wet soil"],
                contradicting_evidence=[],
                distinguishing_test="Unpot the plant and inspect the roots for softness.",
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
                action="Stop watering until the top three centimetres are dry.",
                rationale="Standing water at the roots is what caused this.",
                success_signal="No new yellow leaves within a week.",
                tier=IPMTier.CULTURAL,
                day_offset=0,
            )
        ]
    )


@pytest.fixture
def api_settings():
    return Settings(_env_file=None, openrouter_api_key="sk-test")


@pytest.fixture
def make_service(db):
    """A PlantService for a given owner, on the test session."""

    def _make(user_id) -> PlantService:
        return PlantService(
            user_id=user_id,
            plants=PlantRepository(db),
            observations=ObservationRepository(db),
            diagnoses=DiagnosisRepository(db),
            roadmap=RoadmapRepository(db),
            feedback=FeedbackRepository(db),
            blobs=PostgresBlobStore(db),
            now=lambda: NOW,
        )

    return _make


@pytest.fixture
def client(db, owner, api_settings, make_service):
    """A client whose requests resolve to ``owner`` and run on the test session."""
    app = create_app(api_settings)
    app.dependency_overrides[dependencies.session_dep] = lambda: db
    app.dependency_overrides[dependencies.current_owner] = lambda: owner
    app.dependency_overrides[dependencies.settings_dep] = lambda: api_settings
    app.dependency_overrides[dependencies.plant_service] = lambda: make_service(owner)
    app.dependency_overrides[dependencies.blob_store] = lambda: PostgresBlobStore(db)

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded(db, owner):
    """One plant with a diagnosis, a roadmap step, a message and a photograph."""
    plants = PlantRepository(db)
    blobs = PostgresBlobStore(db)
    photo_key = blobs.put(owner, bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"pixels", "image/png")

    plant_id = plants.create(
        owner,
        name="Kitchen basil",
        species="Ocimum basilicum",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=str(photo_key),
        now=NOW,
    )
    observation_id = ObservationRepository(db).create(
        owner,
        plant_id=plant_id,
        kind="initial",
        photo_refs=[str(photo_key)],
        user_notes=None,
        now=NOW,
    )
    diagnosis_id = DiagnosisRepository(db).create(
        owner,
        observation_id=observation_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="No other plants at risk."),
        retrieved=[],
        model="test-model",
        now=NOW,
    )
    step_ids = RoadmapRepository(db).create_from_roadmap(
        owner, diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=NOW
    )
    message_id = MessageRepository(db).create(
        owner, plant_id=plant_id, role="user", content="Is this normal?", tool_calls=None, now=NOW
    )
    # Committed, not merely flushed. A service refusing a write rolls its transaction
    # back — `PlantService.rename_plant` wraps the repository call — and an uncommitted
    # fixture lives inside that same transaction, so a refused request would discard the
    # very records the test is about to assert on. Committing here releases the savepoint
    # while the fixture's outer transaction still undoes everything at teardown, which is
    # also closer to the truth: this is data that already existed when the request arrived.
    db.commit()
    return {
        "plant_id": plant_id,
        "observation_id": observation_id,
        "diagnosis_id": diagnosis_id,
        "step_id": step_ids[0],
        "message_id": message_id,
        "photo_key": photo_key,
    }
