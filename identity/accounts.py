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
from data.repositories.errors import RecordNotFoundError
from identity import email_tokens, messages, sessions
from identity.passwords import UNUSABLE, hash_password, needs_rehash
from identity.passwords import verify as verify_password

logger = logging.getLogger(__name__)


class RegistrationError(Exception):
    """Registration was refused for a reason the caller can fix.

    ``field`` names the part of the request at fault, so a client can put the message on the
    control that caused it rather than at the top of a form, away from the thing to change.
    """

    field: str | None = None


class WeakPasswordError(RegistrationError):
    """Shorter than the configured minimum.

    Length only. A composition rule ("one digit, one symbol") pushes people towards
    `Password1!` and buys less than the same characters spent on length.
    """

    field = "password"


class ConsentRequiredError(RegistrationError):
    """The privacy notice was not agreed to."""

    field = "accepted_privacy_notice"


class PasswordChangeError(Exception):
    """A password change refused for a reason the caller can fix.

    ``field`` names the box at fault, so a screen can put the message under it rather than
    at the top of a form with three password inputs in it — where "that is not correct"
    would be ambiguous between all three.
    """

    field: str | None = None


class WrongPasswordError(PasswordChangeError):
    """The current password given does not match the account's.

    Said plainly, on the same reasoning as deletion: the caller is already authenticated as
    this account, so confirming which password it has reveals nothing their session does not
    already establish.
    """

    field = "current_password"


class WeakNewPasswordError(PasswordChangeError):
    """The replacement is shorter than the configured minimum."""

    field = "new_password"


class AuthenticationError(Exception):
    """Sign-in was refused.

    One exception for every reason — unknown address, wrong password, unverified account —
    because the caller gets one answer for all of them.
    """


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
    with transaction(session):
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
    """Issue a fresh verification link and mail it.

    Committed before it is sent. A link that arrives before the row it names exists is a
    link that does not work, and the window is small enough to be missed in testing and
    reliable enough to hit somebody in production.
    """
    with transaction(session):
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


def authenticate(session: Session, *, email: str, password: str) -> User:
    """The account signing in, or a refusal that does not say why.

    Unknown address, wrong password and unverified account are one answer. Separating them
    turns sign-in into a way to ask who has an account here, and the third one additionally
    says whether that person has read their email.

    A missing account still pays for a hash. Argon2 takes long enough to measure, and a
    sign-in that returns fast for unknown addresses and slowly for known ones has answered
    the question the identical response was refusing to answer.
    """
    address = normalise(email)
    user = session.scalar(select(User).where(func.lower(User.email) == address))

    if user is None:
        verify_password(password, UNUSABLE)
        raise AuthenticationError("those credentials were not accepted")

    if not verify_password(password, user.password_hash):
        raise AuthenticationError("those credentials were not accepted")

    if user.verified_at is None:
        raise AuthenticationError("those credentials were not accepted")

    if needs_rehash(user.password_hash):
        # The parameters have been raised since this hash was made. Signing in is the only
        # moment the plaintext exists, so it is the only chance to upgrade it.
        with transaction(session):
            user.password_hash = hash_password(password)

    return user


class ResetError(Exception):
    """A reset link could not be honoured."""


def request_reset(session: Session, *, email: str, settings: Settings, mailer: Mailer) -> None:
    """Send a reset link, if there is anywhere to send it.

    Answers the same way for an address with no account: nothing is sent, nothing is
    written, and the caller cannot tell. An endpoint that behaved differently would be a
    way to ask this system who has an account, available to anybody with a list of
    addresses.

    Issuing retires any outstanding reset token, so a link abandoned in an old inbox cannot
    be used later against the person who abandoned it.
    """
    address = normalise(email)
    user = session.scalar(select(User).where(func.lower(User.email) == address))
    if user is None:
        return

    with transaction(session):
        token = email_tokens.issue(
            session,
            user_id=user.id,
            purpose=email_tokens.RESET,
            lifetime_hours=settings.reset_token_hours,
        )

    mailer.send(
        messages.compose(
            user.email,
            messages.password_reset(
                base_url=settings.app_url, token=token, hours=settings.reset_token_hours
            ),
        )
    )


def reset_password(session: Session, *, presented: str, password: str, settings: Settings) -> UUID:
    """Spend a reset link and set a new password.

    Every existing session ends. Somebody resetting a password they may not have chosen to
    forget is the case this protects, and leaving their sessions alive would leave the
    reason for the reset signed in.

    The account is also marked verified if it was not. Following a link that only arrives
    by email is the same proof that verification asks for, and refusing to accept it here
    would leave an unverified account that has proved its address unable to sign in.
    """
    if len(password) < settings.minimum_password_length:
        raise WeakPasswordError(
            f"a password must be at least {settings.minimum_password_length} characters"
        )

    try:
        token = email_tokens.find(session, presented=presented, purpose=email_tokens.RESET)
    except email_tokens.EmailTokenError as exc:
        raise ResetError(str(exc)) from exc

    with transaction(session):
        user_id = email_tokens.spend(session, token)
        user = session.get(User, user_id)
        if user is None:  # pragma: no cover - only if an account is deleted mid-flight
            raise ResetError("no such account")
        user.password_hash = hash_password(password)
        if user.verified_at is None:
            user.verified_at = datetime.now(UTC)
        sessions.revoke_all_for_user(session, user.id)
    return user_id


def change_password(
    session: Session,
    *,
    user_id: UUID,
    current: str,
    new: str,
    settings: Settings,
    keep_family: UUID | None = None,
) -> None:
    """Replace a signed-in account's password, having checked the one it replaces.

    The current password is what proves this is the account's owner and not somebody who
    found the screen unlocked. It is the whole reason this is not simply "set a new
    password" — an unattended session could otherwise be used to lock the owner out of
    their own account.

    Every other session ends. Whoever prompted the change must not still be signed in when
    it is over, and `keep_family` is what spares the one making it.
    """
    user = session.get(User, user_id)
    if user is None:  # pragma: no cover - only if the account is deleted mid-request
        raise RecordNotFoundError("no such account")

    if not verify_password(current, user.password_hash):
        raise WrongPasswordError("that password is not correct")

    if len(new) < settings.minimum_password_length:
        raise WeakNewPasswordError(
            f"a password must be at least {settings.minimum_password_length} characters"
        )

    with transaction(session):
        user.password_hash = hash_password(new)
        sessions.revoke_all_for_user(session, user.id, keep=keep_family)
