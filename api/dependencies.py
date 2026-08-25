"""What a request is given: a session, an owner, and services built around them.

**One session per request.** Opened when the request arrives, closed when the response is
done. Not cached process-wide the way ``ui/bootstrap.py`` caches them — that is correct
for Streamlit, which serves one owner from one process, and wrong here for two reasons: a
cached service would pin an owner into a process serving many, and a single SQLAlchemy
session is not safe to share across concurrent requests.

**One place resolves the owner.** ``current_owner`` is the seam authentication replaces.
It returns the seeded owner today; the next change replaces its body with a token check
and edits nothing else, which is why every handler depends on it rather than reaching for
the owner itself.
"""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session

from agent.wiring import build_deps, default_owner_id, now_utc, open_session
from core.blobs import BlobStore, PostgresBlobStore
from core.config import Settings, get_settings
from core.mail import Mailer, build_mailer
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.feedback import FeedbackRepository
from data.repositories.messages import MessageRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.profile import ProfileRepository
from data.repositories.roadmap import RoadmapRepository
from services.chat_service import ChatService
from services.plant_service import PlantService
from services.profile_service import ProfileService


def settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dep)]


def session_dep(settings: SettingsDep) -> Iterator[Session]:
    """A session for the life of one request.

    Closed in a ``finally`` so a handler that raises still returns its connection to the
    pool — a leak here exhausts the pool after a few dozen failures rather than
    immediately, which is the kind of fault that only shows up under load.
    """
    session = open_session(settings)
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(session_dep)]


def mailer_dep(settings: SettingsDep) -> Mailer:
    """Where email goes.

    The console unless a provider is configured, which is why a machine that has never been
    given a key cannot mail a real person.
    """
    return build_mailer(settings)


MailerDep = Annotated[Mailer, Depends(mailer_dep)]


def current_owner(session: SessionDep) -> UUID:
    """Whose request this is.

    The seeded owner, until authentication exists. **This function is the seam.** Handlers
    take the result and never ask how it was determined, so introducing real sessions
    changes how an owner is established and nothing about what happens afterwards.
    """
    return default_owner_id(session)


OwnerDep = Annotated[UUID, Depends(current_owner)]


def plant_service(session: SessionDep, owner: OwnerDep) -> PlantService:
    return PlantService(
        user_id=owner,
        plants=PlantRepository(session),
        observations=ObservationRepository(session),
        diagnoses=DiagnosisRepository(session),
        roadmap=RoadmapRepository(session),
        feedback=FeedbackRepository(session),
        blobs=PostgresBlobStore(session),
        now=now_utc,
    )


PlantServiceDep = Annotated[PlantService, Depends(plant_service)]


def profile_service(session: SessionDep, owner: OwnerDep) -> ProfileService:
    from core.llm import build_gate_model

    return ProfileService(
        user_id=owner,
        repo=ProfileRepository(session),
        gate_model=build_gate_model(),
        now=now_utc,
    )


ProfileServiceDep = Annotated[ProfileService, Depends(profile_service)]


def blob_store(session: SessionDep) -> BlobStore:
    """The photograph store.

    The one dependency that is not a service. No service owns image bytes — uploads go
    through ``core.images`` and reads are a key lookup — so the photograph route talks to
    the port directly. It takes the owner the same way everything else does; this is an
    exception about *layering*, not about scoping.
    """
    return PostgresBlobStore(session)


BlobStoreDep = Annotated[BlobStore, Depends(blob_store)]


def chat_service(session: SessionDep, owner: OwnerDep, settings: SettingsDep) -> ChatService:
    """Chat, with the agent and its checkpointer behind it.

    Heavier to build than the others — it constructs model clients and a checkpointer — so
    it is a dependency of its own rather than part of a bundle, and only the chat routes
    ask for it.
    """
    from agent.checkpoints import build_checkpointer, checkpointer_url

    profile = profile_service(session, owner)
    deps = build_deps(profile_facts=profile.facts_for_prompt, settings=settings, session=session)
    return ChatService(
        deps=deps,
        messages=MessageRepository(session),
        checkpointer=build_checkpointer(checkpointer_url(settings)),
        now=now_utc,
        profile=profile,
    )


ChatServiceDep = Annotated[ChatService, Depends(chat_service)]

__all__ = [
    "BlobStoreDep",
    "ChatServiceDep",
    "OwnerDep",
    "PlantServiceDep",
    "ProfileServiceDep",
    "SessionDep",
    "SettingsDep",
    "current_owner",
]
