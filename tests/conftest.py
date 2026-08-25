"""Shared pytest fixtures. Populated as tasks add fixtures."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from agent.deps import Deps
from core.blobs import PostgresBlobStore
from core.config import Settings
from core.ids import new_id
from data.models import User
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.roadmap import RoadmapRepository
from knowledge.ingest import load_corpus
from knowledge.retriever import ChromaRetriever, build_vectorstore
from tests.fakes.chat_models import ScriptedStructuredModel
from tests.fakes.embeddings import HashingEmbeddings

# Real-PostgreSQL fixtures, defined in tests/postgres.py so this file stays about
# wiring rather than about database lifecycle. `docker compose up -d db` first.
from tests.postgres import pg_engine, pg_session  # noqa: F401

# The PNG signature, written as byte values rather than escapes. Enough to store and
# read back; no test asserts on pixels.
PNG_BYTES = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"pixels"


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    """Every test runs with a dummy API key so Settings never fails to construct."""
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")


@pytest.fixture
def db(pg_session):  # noqa: F811 — the fixture name is the parameter name
    """A session on the test database, rolled back when the test ends.

    Named ``db`` because it is what several hundred tests already ask for. What it
    hands over changed — a SQLAlchemy session rather than an in-memory SQLite
    connection — but its contract did not: an isolated, empty database per test.
    """
    return pg_session


@pytest.fixture
def owner(db) -> UUID:
    """A seeded owner. Every repository call needs one, so every test needs one."""
    user = User(email=f"{new_id()}@example.test", created_at=datetime.now(UTC))
    db.add(user)
    db.flush()
    return user.id


@pytest.fixture
def other_owner(db) -> UUID:
    """A second owner, for proving that the first one's records are unreachable."""
    user = User(email=f"{new_id()}@example.test", created_at=datetime.now(UTC))
    db.add(user)
    db.flush()
    return user.id


@pytest.fixture
def now():
    """A fixed instant. Never use wall-clock time in tests."""
    fixed = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    return lambda: fixed


@pytest.fixture(scope="session")
def fixture_corpus():
    """Chunks parsed from the real corpus directory."""
    return load_corpus(Path("knowledge/corpus"))


@pytest.fixture
def chroma_retriever(fixture_corpus):
    """An in-memory Chroma retriever over the corpus, using offline embeddings.

    The same ``HashingEmbeddings`` instance serves both paths: it satisfies the
    LangChain ``Embeddings`` interface for text and exposes ``embed_image`` for the
    cross-modal path, so neither path touches a network. A uuid suffix on the
    collection name keeps each test's collection isolated from every other test.
    """
    embeddings = HashingEmbeddings()
    store = build_vectorstore(
        chunks=fixture_corpus,
        embeddings=embeddings,
        collection_name=f"test-corpus-{uuid.uuid4().hex}",
    )
    return ChromaRetriever(store, embeddings)


@pytest.fixture
def make_deps(db, owner, now, chroma_retriever):
    """Factory returning a Deps wired entirely with fakes.

    Override any field per test, for example::

        deps = make_deps(vision_model=ScriptedStructuredModel([guess]))
    """

    def _make(**overrides) -> Deps:
        defaults = {
            "settings": Settings(openrouter_api_key="sk-test", _env_file=None),
            "user_id": owner,
            "gate_model": ScriptedStructuredModel([]),
            "vision_model": ScriptedStructuredModel([]),
            "chat_model": ScriptedStructuredModel([]),
            "retriever": chroma_retriever,
            "blobs": PostgresBlobStore(db),
            "plants": PlantRepository(db),
            "observations": ObservationRepository(db),
            "diagnoses": DiagnosisRepository(db),
            "roadmap": RoadmapRepository(db),
            "weather": lambda location, days: None,
            "web_search": lambda query: [],
            "care_profile": lambda species: None,
            "profile_facts": lambda: "",
            "now": now,
        }
        return Deps(**{**defaults, **overrides})

    return _make


@pytest.fixture
def sample_images(db, owner):
    """One tiny valid PNG, stored so the vision call can actually load it.

    The graph carries a key, not the bytes — so a fixture that invented a key without
    putting anything behind it would make every vision call raise ImageMissingError.
    """
    from agent.state import ImageRef

    key = PostgresBlobStore(db).put(owner, PNG_BYTES, "image/png")
    return [ImageRef(ref=key, media_type="image/png")]


@pytest.fixture
def sample_plant(db, owner, now) -> UUID:
    """A plant with one prior diagnosis and a partially completed roadmap — the
    standard re-check starting point."""
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
        name="Kitchen basil",
        species="Basil",
        species_confidence=0.9,
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
        reasoning="Wet soil and lower-leaf yellowing.",
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
                probability=0.3,
                supporting_evidence=["wet soil"],
                contradicting_evidence=[],
                distinguishing_test="Unpot the plant and inspect the roots.",
                severity=Severity.ACT_TODAY,
                transmissible=False,
            ),
        ],
    )
    diagnosis_id = DiagnosisRepository(db).create(
        owner,
        observation_id=observation_id,
        plant_id=plant_id,
        differential=differential,
        contagion=ContagionAssessment(at_risk=False, advice="No other plants at risk."),
        retrieved=[],
        model="test-model",
        now=now(),
    )
    roadmap = Roadmap(
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
                action="Repot into a container with drainage holes.",
                rationale="Standing water at the roots caused this.",
                success_signal="Soil dries out within three days of watering.",
                tier=IPMTier.MECHANICAL,
                day_offset=7,
            ),
        ]
    )
    step_ids = RoadmapRepository(db).create_from_roadmap(
        owner, diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=roadmap, now=now()
    )
    RoadmapRepository(db).mark(owner, step_ids[0], status="done", now=now())
    return plant_id


@pytest.fixture
def pipeline_models():
    """Scripted models covering a full happy-path run, one per tier.

    Returns ``(gate, vision, chat)``:

    - gate answers two calls in order: PlantCheck, ImageQuality
    - vision answers two: SpeciesGuess, SymptomSet
    - chat answers three: QuestionSet, Differential, Roadmap

    Because each model's script is ordered, these fixtures also assert the pipeline's
    call order implicitly: reorder the nodes and the wrong object comes back.
    """
    from agent.schemas import (
        Candidate,
        Differential,
        Hypotheses,
        ImageQuality,
        IPMTier,
        PlantCheck,
        Question,
        QuestionSet,
        Roadmap,
        RoadmapStep,
        Severity,
        SpeciesGuess,
        Symptom,
        SymptomPosition,
        SymptomSet,
    )
    from tests.fakes.chat_models import ScriptedStructuredModel

    gate = ScriptedStructuredModel(
        [
            PlantCheck(is_plant=True, what_it_is="a potted basil plant"),
            ImageQuality(usable=True, problem=None, guidance=None),
        ]
    )

    vision = ScriptedStructuredModel(
        [
            SpeciesGuess(common_name="Basil", scientific_name="Ocimum basilicum", confidence=0.9),
            SymptomSet(
                symptoms=[
                    Symptom(
                        description="Yellowing",
                        position=SymptomPosition.LOWER_LEAVES,
                        severity=Severity.ACT_THIS_WEEK,
                    )
                ],
                soil_condition="wet",
                overall_vigor="declining",
            ),
        ]
    )

    chat = ScriptedStructuredModel(
        [
            QuestionSet(
                questions=[Question(key="light_hours", text="How much light?", kind="text")]
            ),
            Hypotheses(doc_ids=["overwatering", "root-rot"], reasoning="scripted"),
            Differential(
                is_healthy=False,
                reasoning="Wet soil and lower-leaf yellowing.",
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
                        contradicting_evidence=["firm stem"],
                        distinguishing_test="Unpot the plant and inspect the roots.",
                        severity=Severity.ACT_TODAY,
                        transmissible=False,
                    ),
                ],
            ),
            Roadmap(
                steps=[
                    RoadmapStep(
                        ordinal=1,
                        action="Stop watering until the top 3 cm is dry.",
                        rationale="Lets the roots breathe.",
                        success_signal="No new yellow leaves.",
                        tier=IPMTier.CULTURAL,
                        day_offset=0,
                    )
                ]
            ),
        ]
    )
    return gate, vision, chat
