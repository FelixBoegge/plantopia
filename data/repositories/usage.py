"""What runs have cost, and to whom.

Two kinds of question live here and they are deliberately named differently. Most of this
repository is owner-scoped like every other one — ``user_id`` first, and nothing crosses
between people. ``total_spend_since`` is not: it asks what *everybody* has spent, because
the daily cap is a property of the deployment rather than of a person. It is the one method
here that is allowed to see across owners, and it returns a number rather than any rows, so
it cannot become a way to read somebody else's history.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.cost import UsageSnapshot
from data.models import UsageEvent


class UsageRepository:
    """Reads and writes the record of what has been spent."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        user_id: UUID,
        *,
        kind: str,
        usage: UsageSnapshot | None,
        succeeded: bool,
        now: datetime,
    ) -> UUID:
        """Write what one run cost.

        ``usage`` of ``None`` records a run that made no measurable model call — still a
        run, still counted against the allowance, because a quota that only counts runs the
        provider reported on is one that can be evaded by making it not report.
        """
        event = UsageEvent(
            user_id=user_id,
            kind=kind,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            cost_usd=usage.cost_usd if usage else None,
            succeeded=succeeded,
            occurred_at=now,
        )
        self.session.add(event)
        self.session.flush()
        return event.id

    def count_runs(self, user_id: UUID, *, kind: str, since: datetime) -> int:
        """How many runs of one kind this owner has started since a moment.

        Counts failed runs too. A quota that cannot see them is one somebody can exhaust
        the budget through by failing repeatedly.
        """
        return self.session.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(
                UsageEvent.user_id == user_id,
                UsageEvent.kind == kind,
                UsageEvent.occurred_at >= since,
            )
        )

    def total_spend_since(self, moment: datetime) -> float:
        """What everybody together has spent since a moment.

        Deliberately not owner-scoped — see the module docstring. Rows whose cost the
        provider never reported contribute nothing, which understates rather than
        overstates: a cap that guessed at unmeasured runs would refuse people on the
        strength of a number nobody measured.
        """
        return self.session.scalar(
            select(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0)).where(
                UsageEvent.occurred_at >= moment
            )
        )
