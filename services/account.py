"""What a person is told about their own account.

One place, because the answer is assembled from three: who they are, what they may reach,
and how much of their allowance is left. A screen needs all three and a client that had to
make three requests to draw one page would be a client racing itself.

**Nothing here crosses to another account.** Every value is read for the owner making the
request, and the shape carries no hash, no token and no identifier belonging to anybody
else.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import Settings
from data.models import User
from data.repositories.errors import RecordNotFoundError
from data.repositories.usage import UsageRepository
from services import limits


@dataclass(frozen=True, slots=True)
class Account:
    """A person's own view of themselves."""

    id: UUID
    email: str
    created_at: datetime
    tier: str
    role: str
    consent_version: str
    consent_at: datetime
    runs_used: int
    runs_allowed: int
    allowance_resets_at: datetime


def describe(session: Session, *, user_id: UUID, settings: Settings, now: datetime) -> Account:
    """Everything an account screen needs, in one read.

    The allowance is computed with the same functions the quota guard uses rather than
    recalculated here. Two implementations of "how many runs are left" would eventually
    disagree, and the way somebody would find out is being refused a run the interface had
    just told them they could make.
    """
    user = session.scalar(select(User).where(User.id == user_id))
    if user is None:  # pragma: no cover - a session names an account that exists
        raise RecordNotFoundError("no such account")

    usage = UsageRepository(session)
    return Account(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        tier=user.tier,
        role=user.role,
        consent_version=user.consent_version,
        consent_at=user.consent_at,
        runs_used=usage.count_runs(user_id, kind=limits.DIAGNOSIS, since=limits.period_start(now)),
        runs_allowed=limits.allowance_for(user.tier, settings),
        allowance_resets_at=limits.period_end(now),
    )
