"""What a request is given: a session, an owner, and services built around them.

**One session per request.** Opened when the request arrives, closed when the response is
done. Never cached process-wide, for two reasons: a cached service would pin one owner
into a process serving many, and a single SQLAlchemy session is not safe to share across
concurrent requests.

**One place resolves the owner.** ``current_owner`` is the seam authentication replaces.
It returns the seeded owner today; the next change replaces its body with a token check
and edits nothing else, which is why every handler depends on it rather than reaching for
the owner itself.
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent import checkpoints
from agent.wiring import build_deps, now_utc, open_session
from api import rate_limit
from core.blobs import BlobStore, PostgresBlobStore
from core.config import Settings, get_settings
from core.mail import Mailer, build_mailer
from data.repositories.corpus import CorpusRepository
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.errors import RecordNotFoundError
from data.repositories.feedback import FeedbackRepository
from data.repositories.messages import MessageRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.profile import ProfileRepository
from data.repositories.roadmap import RoadmapRepository
from data.repositories.runs import RunRepository
from data.repositories.usage import UsageRepository
from identity.roles import MEMBER, may_read_evaluations
from identity.tokens import TokenExpiredError, TokenInvalidError, read_access_token
from runs.bus import bus
from runs.executor import RunExecutor, ThreadPoolRunExecutor
from services.chat_service import ChatService
from services.plant_service import PlantService
from services.profile_service import ProfileService
from services.run_service import RunService


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


def rate_limited(request: Request, settings: SettingsDep) -> None:
    """Refuse a source that has called a cheap-to-hammer endpoint too often.

    Declared as a dependency rather than middleware so that which endpoints are limited is
    visible where they are defined, instead of in a path list somewhere else that drifts.
    """
    rate_limit.limit(request, settings)


RateLimited = Depends(rate_limited)


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


def plant_service(session: SessionDep, owner: OwnerDep, settings: SettingsDep) -> PlantService:
    return PlantService(
        user_id=owner,
        plants=PlantRepository(session),
        observations=ObservationRepository(session),
        diagnoses=DiagnosisRepository(session),
        roadmap=RoadmapRepository(session),
        feedback=FeedbackRepository(session),
        corpus=CorpusRepository(session),
        blobs=PostgresBlobStore(session),
        now=now_utc,
        forget_conversation=lambda thread_id: checkpoints.delete_thread(
            checkpoints.checkpointer_url(settings), thread_id
        ),
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


def run_service(session: SessionDep, owner: OwnerDep, settings: SettingsDep) -> RunService:
    """One owner's runs.

    The executor and the bus are process-wide singletons rather than per-request objects:
    a pool built per request would be a pool of one that nothing ever reuses, and a bus
    built per request would publish to nobody, because the watcher subscribed on a
    different one.
    """
    return RunService(
        user_id=owner,
        tier=_tier_of(session, owner),
        runs=RunRepository(session),
        plants=PlantRepository(session),
        usage=UsageRepository(session),
        executor=executor_for(settings),
        bus=bus,
        settings=settings,
        now=now_utc,
    )


RunServiceDep = Annotated[RunService, Depends(run_service)]


def require_evaluation_access(session: SessionDep, owner: OwnerDep, settings: SettingsDep) -> UUID:
    """The owner, if their account may read the evaluation results.

    Raises ``RecordNotFoundError`` otherwise, which the error layer turns into a 404. Not a
    403: a response that distinguishes "you may not" from "there is nothing here" tells a
    stranger the route exists, and the whole interface answers that question the same way
    everywhere else.

    Read per request rather than carried in the token, for the same reason the tier is: a
    role revoked should take effect on the next request, not whenever a token happens to
    expire. ``evaluation_open_to_members`` is read the same way and for the same reason —
    closing the page again should take effect on the next request, not on the next restart.
    """
    if not may_read_evaluations(
        _role_of(session, owner), open_to_members=settings.evaluation_open_to_members
    ):
        raise RecordNotFoundError("no such resource")
    return owner


EvaluationAccessDep = Annotated[UUID, Depends(require_evaluation_access)]


def _role_of(session: Session, owner: UUID) -> str:
    """What this account may reach. Unknown accounts get the ordinary role, which permits
    nothing beyond what ownership already permits."""
    from data.models import User

    return session.scalar(select(User.role).where(User.id == owner)) or MEMBER


def _tier_of(session: Session, owner: UUID) -> str:
    """Which allowance applies to this person.

    Read per request rather than carried in the token: a tier change should take effect on
    the next run, and a tier baked into a token takes effect whenever that token happens to
    expire.
    """
    from data.models import User

    return session.scalar(select(User.tier).where(User.id == owner)) or "free"


def executor_for(settings: Settings) -> RunExecutor:
    """The process's pool.

    One per (size, limit) rather than one absolutely, so a test constructing an application
    with a different pool size gets its own instead of silently inheriting one. Keyed on
    those two scalars because ``Settings`` is not hashable — and because they are what
    actually determines a pool.
    """
    return _pool_for(settings.run_pool_size, settings.run_queue_limit)


@lru_cache(maxsize=4)
def _pool_for(pool_size: int, queue_limit: int) -> RunExecutor:
    return ThreadPoolRunExecutor(pool_size=pool_size, queue_limit=queue_limit)


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
