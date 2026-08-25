"""Making runs in tests.

Here rather than in a conftest because several tiers need it, and because a run has enough
required columns that hand-building one in each test is how a schema change turns into
twenty broken tests that are all the same break.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from data.models import Run

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def make_run(
    session: Session,
    user_id: UUID,
    *,
    plant_id: UUID | None = None,
    kind: str = "diagnosis",
    status: str = "queued",
    thread_id: str | None = None,
    now: datetime = NOW,
    **overrides,
) -> Run:
    """A run belonging to somebody, in whatever state the test needs."""
    run = Run(
        user_id=user_id,
        plant_id=plant_id,
        kind=kind,
        thread_id=thread_id or f"{user_id}:{kind}:test",
        status=status,
        created_at=now,
        status_changed_at=now,
        **overrides,
    )
    session.add(run)
    session.flush()
    return run
