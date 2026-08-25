"""Creating an account and proving its address.

**Registration answers the same way whether or not the address is taken.** An endpoint that
says "already registered" is a way to ask this system who has an account, and that answer is
worth more to somebody enumerating addresses than the convenience is worth to a person who
mistyped theirs. The person who does own the address is told — by email, where they are the
only one reading.

**Registration does not fail because email did.** The account is created either way; the
message can be requested again, and a lost registration cannot be undone.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import Settings
from core.mail import Mailer
from data.engine import transaction
from data.models import User
from identity import email_tokens, messages
from identity.passwords import hash_password

logger = logging.getLogger(__name__)


class RegistrationError(Exception):
    """Registration was refused for a reason the caller can fix."""


class WeakPasswordError(RegistrationError):
    """Shorter than the configured minimum.

    Length only. A composition rule ("one digit, one symbol") pushes people towards
    `Password1!` and buys less than the same characters spent on length.
    """


class ConsentRequiredError(RegistrationError):
    """The privacy notice was not agreed to."""


class VerificationError(Exception):
    """A verification link could not be honoured."""


def register(
    session: Session,
    *,
    email: str,
    password: str,
    consented: bool,
    settings: Settings,
    mailer: Mailer,
) -> None:
    """Create an unverified account and send the address a way to prove itself.

    Returns nothing on purpose: there is no per-outcome result to hand back, because every
    outcome that reaches the caller is the same outcome.
    """
    if not consented:
        raise ConsentRequiredError("the privacy notice must be agreed to")
    if len(password) < settings.minimum_password_length:
        raise WeakPasswordError(
            f"a password must be at least {settings.minimum_password_length} characters"
        )

    address = normalise(email)
    existing = session.scalar(select(User).where(func.lower(User.email) == address))
    if existing is not None:
        # Hashing anyway would be the usual timing defence, but registration already sends
        # mail on both paths and the send dominates anything argon2 contributes.
        mailer.send(
            messages.compose(address, messages.already_registered(base_url=settings.app_url))
        )
        return

    now = datetime.now(UTC)
    user = User(
        email=address,
        password_hash=hash_password(password),
        created_at=now,
        verified_at=None,
        consent_version=settings.consent_version,
        consent_at=now,
    )
    session.add(user)
    session.flush()

    send_verification(session, user=user, settings=settings, mailer=mailer)


def send_verification(session: Session, *, user: User, settings: Settings, mailer: Mailer) -> None:
    """Issue a fresh verification link and mail it."""
    token = email_tokens.issue(
        session,
        user_id=user.id,
        purpose=email_tokens.VERIFY,
        lifetime_hours=settings.verification_token_hours,
    )
    delivered = mailer.send(
        messages.compose(
            user.email,
            messages.verification(
                base_url=settings.app_url,
                token=token,
                hours=settings.verification_token_hours,
            ),
        )
    )
    if not delivered:
        logger.warning("account %s was created but its verification message was not sent", user.id)


def verify(session: Session, *, presented: str) -> UUID:
    """Spend a verification link and mark the account verified.

    Verifying an account that is already verified is refused, because the token was already
    spent — but the account stays verified. The link is single-use; the state it produced is
    not undone by a second click.
    """
    try:
        token = email_tokens.find(session, presented=presented, purpose=email_tokens.VERIFY)
    except email_tokens.EmailTokenError as exc:
        raise VerificationError(str(exc)) from exc

    with transaction(session):
        user_id = email_tokens.spend(session, token)
        user = session.get(User, user_id)
        if user is None:  # pragma: no cover - only if an account is deleted mid-flight
            raise VerificationError("no such account")
        if user.verified_at is None:
            user.verified_at = datetime.now(UTC)
            session.flush()
    return user_id


def normalise(email: str) -> str:
    """One canonical form for an address.

    Lowercased and trimmed, so `Ada@Example.com ` and `ada@example.com` are one account
    rather than two. Nothing beyond that: stripping dots or `+tags` is a provider-specific
    guess, and guessing wrong silently merges two people.
    """
    return email.strip().lower()
