"""Shared pytest fixtures. Populated as tasks add fixtures."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from agent.deps import Deps
from core.blobs import PostgresBlobStore
from core.config import Settings
from data.models import CorpusChunk
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.roadmap import RoadmapRepository
from knowledge.ingest import chunk_text, load_corpus
from knowledge.pgvector_retriever import PgVectorRetriever
from tests.fakes.chat_models import ScriptedStructuredModel
from tests.fakes.embeddings import HashingEmbeddings

# Real-PostgreSQL fixtures, defined in tests/postgres.py so this file stays about
# wiring rather than about database lifecycle. `docker compose up -d db` first.
from tests.people import make_owner
from tests.postgres import pg_engine, pg_session  # noqa: F401
from tests.secrets import TEST_JWT_SECRET

# The PNG signature, written as byte values rather than escapes. Enough to store and
# read back; no test asserts on pixels.
PNG_BYTES = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"pixels"


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    """Every test runs with the two values Settings has no default for.

    ``jwt_secret`` has no default deliberately — a generated one would log everybody out
    on restart in production — so tests must supply it like any other deployment does.
    """
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("PLANTOPIA_JWT_SECRET", TEST_JWT_SECRET)


@pytest.fixture(autouse=True)
def _a_clean_rate_limit_window():
    """Rate-limit counters are process state, shared by every test in the run.

    Without this the suite hits the limit partway through and several dozen unrelated tests
    start answering 429 — a failure whose cause is nowhere near where it shows up.
    """
    from api.rate_limit import window

    window.forget()
    yield
    window.forget()


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
    """A person. Every repository call needs one, so every test needs one."""
    return make_owner(db)


@pytest.fixture
def other_owner(db) -> UUID:
    """A second person, for proving the first one's records are unreachable."""
    return make_owner(db)


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
def corpus_retriever(db, fixture_corpus):
    """A retriever over the real corpus, embedded offline into the test database.

    ``HashingEmbeddings`` rather than the provider, so nothing touches a network and the
    ranking is still meaningful — cosine similarity between two of its vectors reflects
    real word overlap. ``content`` is ``chunk_text`` because that is the string both this
    and ``knowledge.ingest_corpus`` embed; a different string would be a different vector.

    Rows go into the per-test transaction, so each test gets the corpus and none of them
    sees another's. This replaced an in-memory Chroma collection when Chroma was deleted;
    the two were compared over all 87 golden-set queries first and returned identical
    passages at every rank.
    """
    texts = [chunk_text(chunk) for chunk in fixture_corpus]
    embeddings = HashingEmbeddings()
    vectors = embeddings.embed_documents(texts)
    db.add_all(
        [
            CorpusChunk(
                doc_id=chunk.doc_id,
                section=chunk.section,
                name=chunk.name,
                content=text,
                category=chunk.category,
                transmissible=chunk.transmissible,
                severity=chunk.severity,
                embedding=vector,
            )
            for chunk, text, vector in zip(fixture_corpus, texts, vectors, strict=True)
        ]
    )
    db.flush()
    return PgVectorRetriever(db, embeddings)


@pytest.fixture
def make_deps(db, owner, now, corpus_retriever):
    """Factory returning a Deps wired entirely with fakes.

    Override any field per test, for example::

        deps = make_deps(vision_model=ScriptedStructuredModel([guess]))
    """

    def _make(**overrides) -> Deps:
        defaults = {
            "settings": Settings(
                openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET, _env_file=None
            ),
            "user_id": owner,
            "gate_model": ScriptedStructuredModel([]),
            "vision_model": ScriptedStructuredModel([]),
            "chat_model": ScriptedStructuredModel([]),
            "retriever": corpus_retriever,
            "blobs": PostgresBlobStore(db),
            "plants": PlantRepository(db),
            "observations": ObservationRepository(db),
            "diagnoses": DiagnosisRepository(db),
            "roadmap": RoadmapRepository(db),
            "weather": lambda location, days, as_of=None, position=None: None,
            "web_search": lambda query: [],
            # No second identification unless a test asks for one. The same default the
            # application has without a key, so a node test that does not care about
            # identification exercises the path most deployments are on.
            "identify_species": lambda photographs: [],
            # No place name unless a test asks for one, which is the same thing a run gets
            # when the photograph carried no position — the ordinary case.
            "place_name": lambda latitude, longitude: None,
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


def _pipeline_models():
    """Scripted models covering a full happy-path run, one per tier.

    A function rather than a fixture, so a test driving two runs can build two independent
    sets — the scripts are ordered and consumed, and sharing one set between two runs
    exhausts it partway through the second.

    Returns ``(gate, vision, chat)``:

    - gate answers two calls in order: PlantCheck, ImageQuality
    - vision answers two: VisionIdentification, SymptomSet
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
        Symptom,
        SymptomPosition,
        SymptomSet,
        VisionIdentification,
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
            # The identification and what each photograph shows, in one response — which
            # is what `identify_plant` asks for, so that the organs can go to the second
            # identifier without a second model call.
            VisionIdentification(
                common_name="Basil",
                scientific_name="Ocimum basilicum",
                confidence=0.9,
                organs=["leaf"],
            ),
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


@pytest.fixture
def pipeline_models():
    """One set of scripted models, for the many tests that drive a single run."""
    return _pipeline_models()


@pytest.fixture
def make_pipeline_models():
    """A factory, for the few tests that drive more than one run.

    Each set is consumed in order as the graph calls it, so two runs need two sets — a
    shared one runs out partway through the second and fails as a model error rather than
    as whatever the test was about.
    """
    return _pipeline_models
