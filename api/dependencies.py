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

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from agent.wiring import build_deps, now_utc, open_session
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
from identity.tokens import TokenExpiredError, TokenInvalidError, read_access_token
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


class NotSignedInError(Exception):
    """No usable access token was presented."""


class SessionExpiredError(Exception):
    """The access token was ours and is past its lifetime.

    Kept apart from ``NotSignedInError`` because the client's next move differs: this one
    means refresh, the other means sign in again. A client that cannot tell them apart
    either signs people out every fifteen minutes or retries forever.
    """


def current_owner(
    settings: SettingsDep, authorization: Annotated[str | None, Header()] = None
) -> UUID:
    """Whose request this is.

    **This function is the seam.** Handlers take the result and never ask how it was
    determined, which is what let the seeded owner become a real session without touching a
    single handler.

    The token is believed on its signature alone; no row is read. That is the deal a
    stateless token makes, and it is why the lifetime is fifteen minutes: an account deleted
    or disabled mid-token keeps working until the token expires, and shortening that window
    is the only lever there is.
    """
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise NotSignedInError("no access token was presented")

    try:
        return read_access_token(token, secret=settings.jwt_secret)
    except TokenExpiredError as exc:
        raise SessionExpiredError("the access token has expired") from exc
    except TokenInvalidError as exc:
        raise NotSignedInError("the access token could not be read") from exc


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
    deps = build_deps(
        user_id=owner,
        profile_facts=profile.facts_for_prompt,
        settings=settings,
        session=session,
    )
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
