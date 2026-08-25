"""The single-use links that get emailed: issuing one, and spending it.

Verification and reset are the same mechanism with a different purpose string, so they are
one module. Both are stored as hashes, both expire, and both are consumed on first
successful use.

**Issuing invalidates what came before.** Requesting a second reset link retires the first,
so a link abandoned in an old inbox cannot be used later against the person who abandoned
it. It also means a person who requests twice and clicks the older mail sees a refusal,
which is the right trade: the failure is recoverable in one click and the alternative is
not.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import EmailToken
from identity.tokens import fingerprint, has_expired, new_secret_token

VERIFY = "verify"
RESET = "reset"


class EmailTokenError(Exception):
    """A link could not be honoured: unknown, expired, already spent, or the wrong kind."""


def issue(session: Session, *, user_id: UUID, purpose: str, lifetime_hours: int) -> str:
    """Mint a link token and return it in plain form — the only time it exists that way.

    Any outstanding token of the same purpose is retired first.
    """
    invalidate_outstanding(session, user_id=user_id, purpose=purpose)

    secret = new_secret_token()
    now = datetime.now(UTC)
    session.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=fingerprint(secret),
            created_at=now,
            expires_at=now + timedelta(hours=lifetime_hours),
        )
    )
    session.flush()
    return secret


def find(session: Session, *, presented: str, purpose: str) -> EmailToken:
    """The token a link names, if it can be honoured.

    Reads only. A refused link must not open a write transaction: rolling one back to
    achieve nothing is how an unauthenticated endpoint gets to issue database writes.

    Raises ``EmailTokenError`` for anything that cannot be honoured, without distinguishing
    the reasons to the caller — a verification link and a reset link are both things a
    stranger might be holding, and which one failed is not their business.

    The purpose is checked, not assumed: a verification token must not double as a password
    reset, or proving an address would be enough to take the account.
    """
    stored = session.scalar(
        select(EmailToken).where(EmailToken.token_hash == fingerprint(presented))
    )
    if stored is None or stored.purpose != purpose:
        raise EmailTokenError("no such link")
    if stored.used_at is not None:
        raise EmailTokenError("this link has already been used")
    if has_expired(stored.expires_at):
        raise EmailTokenError("this link has expired")
    return stored


def spend(session: Session, token: EmailToken) -> UUID:
    """Mark a token used and return whose it is. Call inside the caller's transaction."""
    token.used_at = datetime.now(UTC)
    session.flush()
    return token.user_id


def invalidate_outstanding(session: Session, *, user_id: UUID, purpose: str) -> int:
    """Retire every unspent token of one purpose. Returns how many."""
    tokens = session.scalars(
        select(EmailToken).where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for token in tokens:
        token.used_at = now
    return len(tokens)
