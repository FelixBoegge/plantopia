"""Building a person, in one place.

``User`` gained required columns when accounts arrived — a password hash, a consent
record — and every fixture that had been writing an email and a timestamp broke at once.
One helper means the next column is one edit rather than a sweep.

The default password hash is the unusable sentinel: a test that wants an account able to
sign in says so, and one that merely needs an owner to scope records to does not
accidentally create a working login.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from core.ids import new_id
from data.models import User
from identity.passwords import UNUSABLE, hash_password


def make_user(
    session: Session,
    *,
    email: str | None = None,
    password: str | None = None,
    verified: bool = True,
    tier: str = "free",
) -> User:
    """Add a person to the database and return the row."""
    now = datetime.now(UTC)
    user = User(
        email=email or f"{new_id()}@example.test",
        password_hash=hash_password(password) if password else UNUSABLE,
        created_at=now,
        verified_at=now if verified else None,
        consent_version="test",
        consent_at=now,
        tier=tier,
    )
    session.add(user)
    session.flush()
    return user


def make_owner(session: Session, **kwargs) -> UUID:
    """Just the identifier, for the many fixtures that only need one."""
    return make_user(session, **kwargs).id
