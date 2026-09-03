"""Sessions: starting one, keeping it alive, and ending it.

A session is a *family* of refresh tokens descended from one sign-in. Each refresh issues
a new token and retires the one presented, so a token is a single-use ticket to the next
one.

**Why families exist.** A retired token being presented again has one likely explanation:
two parties hold it, and only one of them should. There is no way to tell which of them is
asking — the thief's copy is identical to the victim's. Refusing that one request would
leave the newer token working, which is the thief's if they refreshed first. So the whole
family goes and the account signs in again.

**The accepted cost.** A client that blindly retries a refresh after a dropped response
presents a retired token and logs itself out. That is indistinguishable from a theft, and
the frontend contract is therefore that refresh is not retried.

**These functions commit their own work**, unlike the repositories, which leave that to the
caller. They have to: detecting reuse invalidates a family and *then* refuses the request,
and a caller that wrapped the call in one transaction would roll the invalidation back with
the refusal — leaving the thief's token working, which is the one outcome this whole
mechanism exists to prevent.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import Settings
from core.ids import new_id
from data.engine import transaction
from data.models import RefreshToken
from identity.tokens import (
    fingerprint,
    has_expired,
    issue_access_token,
    new_secret_token,
)


class SessionError(Exception):
    """A session could not be established or continued."""


class InvalidRefreshTokenError(SessionError):
    """Unknown, expired, or belonging to a family that has been invalidated."""


class RefreshTokenReusedError(SessionError):
    """A retired token was presented again, and its family has been invalidated.

    Distinct from ``InvalidRefreshTokenError`` for the log's sake rather than the client's —
    both mean "sign in again" to whoever is asking, but only one of them means somebody
    should look at why.
    """


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """What a sign-in or a refresh hands back."""

    access_token: str
    refresh_token: str
    family_id: UUID
    expires_at: datetime


def start(session: Session, *, user_id: UUID, settings: Settings) -> IssuedSession:
    """Begin a new session. Each sign-in starts its own family."""
    with transaction(session):
        issued = _issue(session, user_id=user_id, family_id=new_id(), settings=settings)
    return issued


def refresh(session: Session, *, presented: str, settings: Settings) -> IssuedSession:
    """Exchange a refresh token for the next one.

    Raises ``RefreshTokenReusedError`` when the presented token has already been rotated —
    having first invalidated every token in its family — and ``InvalidRefreshTokenError`` for
    anything else that cannot be honoured.
    """
    stored = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == fingerprint(presented))
    )
    if stored is None:
        raise InvalidRefreshTokenError("no such refresh token")

    if stored.used_at is not None:
        # Two parties hold this token. Which one is asking cannot be determined, so the
        # session ends for both — and the ending is committed before the refusal, or the
        # refusal would undo it.
        with transaction(session):
            revoke_family(session, stored.family_id)
        raise RefreshTokenReusedError("refresh token reused; the session has been ended")

    if stored.revoked_at is not None:
        raise InvalidRefreshTokenError("this session has been ended")

    if has_expired(stored.expires_at):
        raise InvalidRefreshTokenError("this refresh token has expired")

    with transaction(session):
        stored.used_at = datetime.now(UTC)
        issued = _issue(
            session, user_id=stored.user_id, family_id=stored.family_id, settings=settings
        )
    return issued


def end(session: Session, *, presented: str) -> None:
    """Sign out.

    Invalidates the whole family rather than the single token: signing out on a device
    should end that device's session, and every token that device could still rotate into
    belongs to the same family.

    Silent about a token it does not recognise. Signing out is a request to be signed out,
    and reporting that a token was already invalid tells an unauthenticated caller
    something about which tokens exist.
    """
    stored = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == fingerprint(presented))
    )
    if stored is not None:
        with transaction(session):
            revoke_family(session, stored.family_id)


def revoke_family(session: Session, family_id: UUID) -> int:
    """Invalidate every token descended from one sign-in. Returns how many."""
    tokens = session.scalars(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    now = datetime.now(UTC)
    for token in tokens:
        token.revoked_at = now
    return len(tokens)


def family_of(session: Session, presented: str) -> UUID | None:
    """Which sign-in a refresh token belongs to, or `None` if it is not one we issued."""
    stored = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == fingerprint(presented))
    )
    return stored.family_id if stored else None


def revoke_all_for_user(session: Session, user_id: UUID, *, keep: UUID | None = None) -> int:
    """End every session this person has, except optionally one family.

    Used by a password reset with nothing kept: somebody resetting a password they may not
    have chosen to forget is the case that protects, and leaving existing sessions alive
    would leave the reason for the reset in place.

    Used by a password *change* with the caller's own family kept. The same reasoning
    applies to every other device, but signing somebody out of the session they are
    changing their password in punishes them for tidying up.
    """
    tokens = session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            *([RefreshToken.family_id != keep] if keep else []),
        )
    ).all()
    now = datetime.now(UTC)
    for token in tokens:
        token.revoked_at = now
    return len(tokens)


def _issue(
    session: Session, *, user_id: UUID, family_id: UUID, settings: Settings
) -> IssuedSession:
    """Mint an access token and the refresh token that will replace itself."""
    secret_token = new_secret_token()
    now = datetime.now(UTC)
    expires_at = now + _refresh_lifetime(settings)

    session.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=fingerprint(secret_token),
            issued_at=now,
            expires_at=expires_at,
        )
    )
    session.flush()

    return IssuedSession(
        access_token=issue_access_token(
            user_id=user_id,
            secret=settings.jwt_secret,
            lifetime_minutes=settings.access_token_minutes,
        ),
        refresh_token=secret_token,
        family_id=family_id,
        expires_at=expires_at,
    )


def _refresh_lifetime(settings: Settings):
    from datetime import timedelta

    return timedelta(days=settings.refresh_token_days)
