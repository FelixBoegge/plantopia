"""Tokens: the short one a request carries, and the long ones that are stored.

Two different things with different rules, kept in one module because the rules only make
sense next to each other.

**The access token is a signed claim, not a record.** Nothing is stored, so nothing can
revoke it — it is believed until it expires. That is why it is short: its lifetime is
exactly the window a stolen one is useful for.

**Refresh and email tokens are secrets that are stored.** Stored as hashes, so a database
dump is not a set of working sessions and a set of working password-reset links. Compared
by hashing what was presented, never by looking up the plaintext.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

ALGORITHM = "HS256"

# 32 bytes from the system CSPRNG, URL-safe. Long enough that guessing is not a strategy,
# short enough to survive being pasted into a browser bar from an email.
TOKEN_BYTES = 32


class TokenError(Exception):
    """A token could not be accepted. Subclasses say why."""


class TokenExpiredError(TokenError):
    """Valid, but past its lifetime.

    Distinct from ``TokenInvalidError`` on purpose: a client seeing this knows to refresh,
    where a client seeing the other knows to sign in again.
    """


class TokenInvalidError(TokenError):
    """Malformed, tampered with, or signed by something else."""


def issue_access_token(*, user_id: UUID, secret: str, lifetime_minutes: int) -> str:
    """A signed claim that this request belongs to this person.

    ``jti`` is a fresh identifier per token. Nothing reads it yet; it is what a future
    denylist would key on, and it costs nothing to include now while it costs a migration
    to add later.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=lifetime_minutes)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def read_access_token(token: str, *, secret: str) -> UUID:
    """The owner a token names.

    Raises ``TokenExpiredError`` for a token past its life and ``TokenInvalidError`` for everything
    else — tampered, malformed, signed with another key, or naming something that is not
    an identifier.

    The algorithm is pinned. Accepting whatever the token's own header claims is how a
    token signed with ``alg: none`` gets believed.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("the access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalidError("the access token could not be read") from exc

    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenInvalidError("the access token names no valid owner") from exc


def new_secret_token() -> str:
    """A fresh secret to send to somebody: a refresh token, or an emailed link."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def fingerprint(token: str) -> str:
    """What gets stored for a secret token.

    SHA-256 rather than argon2, and deliberately: these are 32 bytes of CSPRNG output,
    not a human-chosen password, so there is nothing for a slow hash to defend against —
    no dictionary, no reuse across sites, no guessing. What is needed is that the stored
    form cannot be replayed, and a fast digest gives that without making every request
    pay argon2's cost.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def matches(token: str, stored_hash: str) -> bool:
    """Whether a presented token is the one stored.

    Compared in constant time. The window is small, but the comparison is free.
    """
    return hmac.compare_digest(fingerprint(token), stored_hash)


def expires_in(*, hours: int = 0, days: int = 0) -> datetime:
    """An absolute expiry, computed once at issue rather than checked as a duration."""
    return datetime.now(UTC) + timedelta(hours=hours, days=days)


def has_expired(expires_at: datetime, *, now: datetime | None = None) -> bool:
    """Whether an expiry has passed.

    Tolerates a naive timestamp by reading it as UTC: everything this project stores is
    timezone-aware, but a value that has been through a serialisation round-trip somewhere
    should not silently compare as being in the future.
    """
    moment = now or datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= moment
