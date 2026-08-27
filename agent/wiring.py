"""Build the real dependencies, outside any UI framework.

Lifted out of ``ui/bootstrap.py``, whose accessors are ``@st.cache_resource``
functions and so only callable from a Streamlit script run. A second entry point
needed the same objects — the LangGraph dev server behind Studio, which builds the
graph itself in a plain Python process — and the one thing worse than wiring in an
awkward place is the same wiring in two places, quietly drifting until Studio shows a
graph the app does not run.

Nothing here caches. Callers decide that: ``ui/bootstrap.py`` wraps these in
``st.cache_resource``, and the dev server builds once at startup.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from agent.deps import Deps
from core.blobs import PostgresBlobStore
from core.config import Settings, get_settings
from core.embeddings import ImageEmbedder
from core.llm import (
    build_embeddings,
    build_gate_model,
    build_reasoning_model,
    build_vision_model,
)
from data.engine import build_engine, build_sessions, transaction
from data.models import User
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.profile import ProfileRepository
from data.repositories.roadmap import RoadmapRepository
from identity.passwords import UNUSABLE
from knowledge.ingest import load_corpus
from knowledge.retriever import ChromaRetriever, build_vectorstore
from services.profile_service import ProfileService
from tools.care_profiles import lookup_plant_care_profile
from tools.plantnet import identify_species as plantnet_identify
from tools.weather import get_local_weather
from tools.web_search import web_search_plant_info

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    """The clock the whole application shares, injected rather than called inline."""
    return datetime.now(tz=UTC)


@lru_cache(maxsize=4)
def _engine_for(url: str) -> Engine:
    """One connection pool per URL, shared by every caller in the process.

    The SQLite version opened a separate connection per caller and relied on a
    module-level write lock to keep them from treading on each other. A pool makes
    that unnecessary: sessions borrow connections and hand them back, and Postgres
    resolves concurrent writers itself.
    """
    return build_engine(url)


def open_session(settings: Settings | None = None) -> Session:
    """A session on the project database.

    The schema is not applied here. ``alembic upgrade head`` owns it, so a process
    that starts against an out-of-date database fails loudly rather than silently
    running on a schema nobody migrated.
    """
    settings = settings or get_settings()
    return build_sessions(_engine_for(settings.database_url))()


# The account developer harnesses run as. Not a person, and named so that it cannot be
# mistaken for one in a list of accounts.
HARNESS_EMAIL = "harness@plantopia.invalid"


def harness_owner_id(session: Session) -> UUID:
    """The owner that the evaluation harness and LangGraph Studio write as.

    Created on demand so neither has a setting to forget. Its password is unusable and it
    is never verified, so nothing can sign in as it — it exists to give ``user_id`` a real
    row to carry in the two entry points that have no request and therefore no session.

    This is not an authentication path and no endpoint reaches it. Endpoints resolve an
    owner from a bearer token in ``api/dependencies.current_owner``, which is the only
    place resolution happens.
    """
    owner = session.scalar(select(User).where(User.email == HARNESS_EMAIL))
    if owner is None:
        with transaction(session):
            now = now_utc()
            owner = User(
                email=HARNESS_EMAIL,
                password_hash=UNUSABLE,
                created_at=now,
                verified_at=None,
                consent_version="harness",
                consent_at=now,
                tier="free",
            )
            session.add(owner)
            session.flush()
    return owner.id


def build_profile_service(*, user_id: UUID, settings: Settings | None = None) -> ProfileService:
    """The learned-profile service, on its own session."""
    settings = settings or get_settings()
    session = open_session(settings)
    return ProfileService(
        user_id=user_id,
        repo=ProfileRepository(session),
        gate_model=build_gate_model(),
        now=now_utc,
    )


def build_deps(
    *,
    user_id: UUID,
    profile_facts: Callable[[], str],
    settings: Settings | None = None,
    session: Session | None = None,
) -> Deps:
    """Everything the graph's nodes need from the outside world.

    Args:
        user_id: Whose run this is. Passed in rather than resolved here, because the
            only place that decides who is asking is the request. Resolving it inside
            this function is how the agent ended up reading one owner's corpus while the
            surrounding request was scoped to another.
        profile_facts: Renders the owner's learned profile for injection into
            prompts. Passed in rather than built here because the profile service is
            also a UI-facing object with its own lifetime, and ``Deps`` deliberately
            declares no default for it (see ``agent/deps.py``).
        settings: Overridable for tests and alternative entry points.
        session: An existing session to use rather than opening one. Callers that
            already have a session must pass it: a request that writes a chat message
            through one session and reads plant history through another sees its own
            uncommitted write as absent, which is a bug that only appears once both
            happen inside one operation.
    """
    settings = settings or get_settings()
    session = session or open_session(settings)

    retriever = _shared_retriever(settings)

    return Deps(
        settings=settings,
        user_id=user_id,
        gate_model=build_gate_model(),
        vision_model=build_vision_model(),
        chat_model=build_reasoning_model(),
        retriever=retriever,
        blobs=PostgresBlobStore(session),
        plants=PlantRepository(session),
        observations=ObservationRepository(session),
        diagnoses=DiagnosisRepository(session),
        roadmap=RoadmapRepository(session),
        weather=lambda location, days, as_of=None: get_local_weather(location, days, as_of=as_of),
        web_search=lambda query: web_search_plant_info(query, api_key=settings.tavily_api_key),
        identify_species=lambda photographs: plantnet_identify(
            photographs, api_key=settings.plantnet_api_key
        ),
        care_profile=lookup_plant_care_profile,
        profile_facts=profile_facts,
        now=now_utc,
    )


def _shared_retriever(settings: Settings) -> ChromaRetriever:
    """The corpus retriever, built once for the process.

    Embedding the corpus and opening the collection is the expensive part of wiring, and
    none of it varies by request or by owner. Built per call it would re-embed on every
    chat message — slow, billable, and in tests a network call the suite forbids.
    """
    return _retriever_for(
        settings.corpus_path,
        settings.chroma_path,
        settings.embedding_model,
        settings.multimodal_embeddings,
        settings.openrouter_api_key,
        settings.openrouter_base_url,
    )


@lru_cache(maxsize=2)
def _retriever_for(
    corpus_path: Path,
    chroma_path: Path,
    embedding_model: str,
    multimodal: bool,
    api_key: str,
    base_url: str,
) -> ChromaRetriever:
    """Keyed on what actually determines a retriever.

    Scalars rather than the ``Settings`` object, which is not hashable — and keying on
    the specific fields is the more honest cache anyway: two settings differing only in,
    say, a diagnosis threshold describe the same retriever.
    """
    vectorstore = build_vectorstore(
        chunks=load_corpus(corpus_path),
        embeddings=build_embeddings(),
        persist_directory=chroma_path,
    )

    # Shares the collection's vector space, which is what makes cross-modal retrieval
    # work. Wired only when the configured embedding model actually accepts images —
    # passing it unconditionally would cost one doomed HTTP call per uploaded image.
    image_embedder = (
        ImageEmbedder(api_key=api_key, base_url=base_url, model=embedding_model)
        if multimodal
        else None
    )
    if image_embedder is None:
        logger.info(
            "cross-modal image retrieval disabled (multimodal_embeddings=False); "
            "diagnosis will use the text retrieval path only"
        )
    return ChromaRetriever(vectorstore, image_embedder)
