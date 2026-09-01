"""Removing an account, and everything that was ever true of it.

The database does most of this. Every foreign key in `data/models.py` declares
``ondelete="CASCADE"``, so deleting the `users` row reaches all seventeen owned tables,
including the six that carry no ``user_id`` and are reachable only through a parent, and
including the photographs. `tests/unit/data/test_deletion_completeness.py` proves that
against `Base.metadata` rather than against a list somebody remembered to update.

What this adds is the two things the schema cannot see:

- **The refresh tokens**, so the session cannot be extended past the deletion.
- **The conversation checkpoints**, which LangGraph owns in its own tables, on its own
  connection, keyed by a thread id rather than by a foreign key.

That second one is why this is honestly *two* atomic operations rather than one, and why
the order below is a decision rather than an accident.
"""

import logging
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from agent import checkpoints
from core.config import Settings
from data.engine import transaction
from data.models import User
from data.repositories.errors import RecordNotFoundError
from identity import sessions
from identity.passwords import verify as verify_password

logger = logging.getLogger(__name__)

# What somebody types to confirm. A fixed word rather than the account's own address: the
# address is more specific and harder to type by reflex, which cuts both ways — somebody
# acting deliberately should not be made to fetch it, and somebody acting carelessly is
# stopped by any typing at all.
CONFIRMATION = "delete my account"


class ConfirmationError(Exception):
    """The password or the typed confirmation did not satisfy the deletion request."""


def confirm_and_delete(
    session: Session,
    *,
    user_id: UUID,
    password: str,
    confirmation: str,
    settings: Settings,
) -> None:
    """Check that somebody meant it, then erase the account.

    The password is verified here rather than in the handler so that the check and the
    deletion cannot be separated by a later caller who forgets one of them.

    Unlike signing in, this may say plainly that the password was wrong: the caller is
    already authenticated as this account, so confirming it reveals nothing the session does
    not already establish.
    """
    user = session.get(User, user_id)
    if user is None:
        raise RecordNotFoundError("no such account")

    if confirmation.strip().casefold() != CONFIRMATION:
        raise ConfirmationError("the confirmation phrase does not match")

    if not verify_password(password, user.password_hash):
        raise ConfirmationError("that password is not correct")

    # The transaction opens only once both checks have passed. Refusing inside it would
    # make a *rejected* deletion roll back whatever else the caller had pending, which is a
    # side effect nobody asked for — and it is how this was found: a test refused correctly
    # and took the fixture's own rows with it.
    with transaction(session):
        delete_account(session, user_id=user_id, settings=settings)


def delete_account(session: Session, *, user_id: UUID, settings: Settings) -> None:
    """Erase an account. Not undoable, and not partially applicable.

    Does not open a transaction of its own — `confirm_and_delete` does, once it is satisfied
    that somebody meant it. A caller reaching this directly is responsible for grouping it.

    **Checkpoints go before the user row, deliberately.** They live on the checkpointer's
    own connection pool, so they cannot join this transaction — which means one of the two
    orders leaves a mess when the other half fails:

    - Checkpoints first, then a failure: an account that still exists whose conversations
      have lost their history. Visible, complainable-about, and recoverable by asking again.
    - User row first, then a failure: checkpoint rows keyed to a user who no longer exists.
      Unreachable by any owner's prefix, invisible to every screen, and never cleaned up.

    The first failure is the one somebody can see, so it is the one this arranges to be
    possible. Everything after the checkpoint sweep is a single transaction the caller
    commits, so the application's own tables are all-or-nothing.
    """
    user = session.get(User, user_id)
    if user is None:
        raise RecordNotFoundError("no such account")

    # Cannot be extended. The access token already issued keeps working until it expires —
    # `api/dependencies.current_owner` reads no row, by design — and that window is
    # recorded rather than closed here.
    revoked = sessions.revoke_all_for_user(session, user_id)

    removed = checkpoints.delete_for_user(checkpoints.checkpointer_url(settings), user_id)

    # And the rest by cascade. Seventeen tables from one statement, which is only
    # trustworthy because a test enumerates them from the schema.
    session.execute(delete(User).where(User.id == user_id))

    logger.info(
        "erased an account: %d sessions revoked, %d checkpoint rows removed", revoked, removed
    )
