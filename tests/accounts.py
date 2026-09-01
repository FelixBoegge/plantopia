"""One account with a row in every table that belongs to somebody.

Deletion is the one operation where "we tested it" and "we tested all of it" are different
claims, and the difference is invisible: a delete that misses a table leaves rows nobody can
reach and nobody is told about. So the test that proves deletion needs an account that is
genuinely full, and something that fails when this helper stops filling every table.

`tests/unit/data/test_deletion_completeness.py` asserts exactly that against
`Base.metadata`, which is why this is a helper rather than a fixture inlined in one test:
the population and the enumeration have to be checkable against each other.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from agent.schemas import Candidate, Differential, IPMTier, Roadmap, RoadmapStep, Severity
from agent.threads import chat_thread, diagnosis_thread
from core.blobs import PostgresBlobStore
from core.config import Settings
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.feedback import FeedbackRepository
from data.repositories.messages import MessageRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.profile import ProfileRepository
from data.repositories.roadmap import RoadmapRepository
from data.repositories.runs import RunRepository
from data.repositories.usage import UsageRepository
from identity import email_tokens, sessions
from tests.people import make_user
from tests.secrets import TEST_JWT_SECRET

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class FullAccount:
    """What was created, for a test that wants to name one of the rows."""

    user_id: UUID
    email: str
    password: str
    plant_id: UUID
    observation_id: UUID
    diagnosis_id: UUID
    step_id: UUID
    message_id: UUID
    run_id: UUID
    photo_key: UUID
    chat_thread_id: str
    diagnosis_thread_id: str


def populate(session: Session, *, password: str = "a-long-enough-password") -> FullAccount:
    """Create an account with a row in every owned table.

    Every table, deliberately — including the ones no single feature test touches together,
    like `email_tokens` and `run_events`. An account missing one of those would let a
    deletion that misses the same one pass.
    """
    user = make_user(session, password=password)
    settings = Settings(jwt_secret=TEST_JWT_SECRET, openrouter_api_key="sk-test", _env_file=None)

    # A session and a pending verification link.
    sessions.start(session, user_id=user.id, settings=settings)
    email_tokens.issue(session, user_id=user.id, purpose="verify", lifetime_hours=24)

    photo_key = PostgresBlobStore(session).put(user.id, b"pretend-jpeg-bytes", "image/jpeg")

    plant_id = PlantRepository(session).create(
        user.id,
        name="Kitchen basil",
        species="Ocimum basilicum",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=str(photo_key),
        now=NOW,
    )
    observation_id = ObservationRepository(session).create(
        user.id,
        plant_id=plant_id,
        kind="initial",
        photo_refs=[str(photo_key)],
        user_notes="Lower leaves yellowing.",
        now=NOW,
    )
    diagnosis_id = DiagnosisRepository(session).create(
        user.id,
        observation_id=observation_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=None,
        retrieved=[],
        model="test-model",
        now=NOW,
    )
    step_ids = RoadmapRepository(session).create_from_roadmap(
        user.id, diagnosis_id=diagnosis_id, plant_id=plant_id, roadmap=_roadmap(), now=NOW
    )
    FeedbackRepository(session).create(
        user.id,
        diagnosis_id=diagnosis_id,
        rating=4,
        did_it_help="yes",
        free_text="The plan worked.",
        now=NOW,
    )

    message_id = MessageRepository(session).create(
        user.id,
        plant_id=plant_id,
        role="user",
        content="Is this normal?",
        tool_calls=None,
        now=NOW,
    )

    profile = ProfileRepository(session)
    profile.upsert(user.id, fact="tends to overwater", source="inferred", confidence=0.7, now=NOW)
    profile.set_cursor(user.id, plant_id=plant_id, last_message_id=message_id)

    UsageRepository(session).record(user.id, kind="diagnosis", usage=None, succeeded=True, now=NOW)

    runs = RunRepository(session)
    thread_id = diagnosis_thread(user.id)
    run_id = runs.create(user.id, plant_id=plant_id, kind="diagnosis", thread_id=thread_id, now=NOW)
    runs.append_event(run_id, kind="started", payload={}, now=NOW)

    session.flush()
    return FullAccount(
        user_id=user.id,
        email=user.email,
        password=password,
        plant_id=plant_id,
        observation_id=observation_id,
        diagnosis_id=diagnosis_id,
        step_id=step_ids[0],
        message_id=message_id,
        run_id=run_id,
        photo_key=photo_key,
        chat_thread_id=chat_thread(user.id, plant_id),
        diagnosis_thread_id=thread_id,
    )


def _differential() -> Differential:
    return Differential(
        candidates=[
            Candidate(
                disorder_id="overwatering",
                name="Overwatering",
                probability=0.7,
                severity=Severity.ACT_THIS_WEEK,
                supporting_evidence=["Yellowing lower leaves"],
                contradicting_evidence=["Soil surface is dry"],
                distinguishing_test="Unpot and look at the roots",
                transmissible=False,
            ),
            # Two, because an unhealthy differential is required to carry two or three —
            # the schema refuses to let the agent name one cause and call it certain.
            Candidate(
                disorder_id="root-rot",
                name="Root rot",
                probability=0.3,
                severity=Severity.ACT_TODAY,
                supporting_evidence=["Soil has stayed wet"],
                contradicting_evidence=["No smell reported"],
                distinguishing_test="Unpot and smell the rootball",
                transmissible=False,
            ),
        ],
        reasoning="The pattern points at the roots.",
        is_healthy=False,
    )


def _roadmap() -> Roadmap:
    return Roadmap(
        steps=[
            RoadmapStep(
                ordinal=1,
                action="Stop watering until the top third is dry",
                rationale="Roots sitting in water cannot take up oxygen",
                success_signal="No new leaves yellow",
                tier=IPMTier.CULTURAL,
                day_offset=0,
            )
        ],
    )
