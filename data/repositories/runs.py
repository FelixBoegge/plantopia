"""Persistence for runs and the events they emit.

Every method takes ``user_id`` first, and every query filters on it — the same signature
every other repository here has, for the same reason: a caller cannot reach another owner's
run without inventing an owner to do it with.

**Status transitions are conditional.** Two things write a run's status: the worker
advancing it, and a request cancelling or answering it. A read-then-write loses one of them
silently, and does so under exactly the timing a test will not reproduce. So every
transition names the status it expects to find, and a caller that finds none knows it lost
the race rather than assuming it won.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from data.models import Run, RunEvent

# The statuses a run can be in, and which of them are the end of it.
QUEUED = "queued"
RUNNING = "running"
AWAITING_ANSWERS = "awaiting_answers"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL = frozenset({COMPLETED, FAILED, CANCELLED})
UNFINISHED = frozenset({QUEUED, RUNNING, AWAITING_ANSWERS})


@dataclass(frozen=True, slots=True)
class RunRecord:
    """A run as a caller sees it. No worker internals, no cancellation flag."""

    id: UUID
    plant_id: UUID | None
    kind: str
    status: str
    created_at: datetime
    status_changed_at: datetime
    finished_at: datetime | None
    diagnosis_id: UUID | None
    error: str | None


@dataclass(frozen=True, slots=True)
class EventRecord:
    """One event, in the order it happened."""

    sequence: int
    kind: str
    payload: dict
    occurred_at: datetime


def _to_record(row: Run) -> RunRecord:
    return RunRecord(
        id=row.id,
        plant_id=row.plant_id,
        kind=row.kind,
        status=row.status,
        created_at=row.created_at,
        status_changed_at=row.status_changed_at,
        finished_at=row.finished_at,
        diagnosis_id=row.diagnosis_id,
        error=row.error,
    )


class RunRepository:
    """Reads and writes ``runs`` and ``run_events``.

    Write methods do not commit; the caller groups writes with ``data.engine.transaction``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def create(
        self,
        user_id: UUID,
        *,
        plant_id: UUID | None,
        kind: str,
        thread_id: str,
        now: datetime,
    ) -> UUID:
        """Record a run before it is queued.

        The row exists before the work is submitted, so a caller handed an identifier can
        always fetch something. ``queued`` is a real state — a full pool is where a run
        genuinely sits — not a placeholder for the gap before ``running``.
        """
        run = Run(
            user_id=user_id,
            plant_id=plant_id,
            kind=kind,
            thread_id=thread_id,
            status=QUEUED,
            created_at=now,
            status_changed_at=now,
        )
        self._session.add(run)
        self._session.flush()
        return run.id

    def get(self, user_id: UUID, run_id: UUID) -> RunRecord | None:
        row = self._row(user_id, run_id)
        return _to_record(row) if row is not None else None

    def list_for_user(self, user_id: UUID, *, limit: int = 50) -> list[RunRecord]:
        """This owner's runs, most recent first."""
        rows = self._session.scalars(
            select(Run)
            .where(Run.user_id == user_id)
            .order_by(Run.created_at.desc(), Run.id.desc())
            .limit(limit)
        ).all()
        return [_to_record(row) for row in rows]

    def thread_of(self, user_id: UUID, run_id: UUID) -> str | None:
        """The checkpoint key, which resuming needs and no client ever sees."""
        row = self._row(user_id, run_id)
        return row.thread_id if row is not None else None

    def advance(
        self,
        run_id: UUID,
        *,
        expected: str | frozenset[str],
        to: str,
        now: datetime,
        **fields,
    ) -> bool:
        """Move a run to a new status, but only from the status it is expected to be in.

        Returns whether it moved. ``False`` means somebody else got there first — a
        cancellation landing between two nodes, or a second answer arriving — and the
        caller decides what that means rather than discovering it later through a row that
        does not say what it wrote.

        Not owner-scoped: the worker holds a run id and has already established ownership
        at the door. Adding an owner here would mean the worker carrying one around solely
        to satisfy a signature, which is the kind of parameter that eventually gets passed
        wrongly.
        """
        expected_statuses = {expected} if isinstance(expected, str) else set(expected)
        values = {"status": to, "status_changed_at": now, **fields}
        if to in TERMINAL:
            values.setdefault("finished_at", now)

        result = self._session.execute(
            update(Run).where(Run.id == run_id, Run.status.in_(expected_statuses)).values(**values)
        )
        return result.rowcount == 1

    def request_cancel(self, user_id: UUID, run_id: UUID) -> bool:
        """Ask a run to stop. Returns whether there was an unfinished run to ask.

        A flag rather than a status: the run is still legitimately ``running`` until the
        worker notices between nodes, and a status meaning "will stop shortly" is one every
        client has to special-case.
        """
        result = self._session.execute(
            update(Run)
            .where(
                Run.id == run_id,
                Run.user_id == user_id,
                Run.status.in_(UNFINISHED),
            )
            .values(cancel_requested=True)
        )
        return result.rowcount == 1

    def cancel_requested(self, run_id: UUID) -> bool:
        """Whether a stop has been asked for. Read by the worker between nodes."""
        return bool(self._session.scalar(select(Run.cancel_requested).where(Run.id == run_id)))

    def status_of(self, run_id: UUID) -> str | None:
        """A run's status without an owner.

        Worker-side, like ``advance``: ownership was established at the door and the worker
        carries a run id, not a person.
        """
        return self._session.scalar(select(Run.status).where(Run.id == run_id))

    def mark_usage_recorded(self, run_id: UUID) -> bool:
        """Claim the right to record this run's usage, once.

        Conditional so that a worker finishing and the sweeper giving up cannot both
        record the same run — which would charge an owner twice for one diagnosis.
        """
        result = self._session.execute(
            update(Run)
            .where(Run.id == run_id, Run.usage_recorded.is_(False))
            .values(usage_recorded=True)
        )
        return result.rowcount == 1

    def unfinished_since_before(self, moment: datetime, *, statuses: frozenset[str]) -> list[UUID]:
        """Runs stuck in one of these statuses since before a moment.

        Not owner-scoped, deliberately: the sweeper is a property of the deployment, like
        the daily spend cap. It returns identifiers rather than rows so it cannot become a
        way to read anybody's history.
        """
        return list(
            self._session.scalars(
                select(Run.id).where(Run.status.in_(statuses), Run.status_changed_at < moment)
            ).all()
        )

    # Events -----------------------------------------------------------------

    def append_event(self, run_id: UUID, *, kind: str, payload: dict, now: datetime) -> int:
        """Write an event and return its sequence.

        The sequence is derived under the same transaction as the insert, so two writers
        cannot both claim one — the unique constraint is what makes that a failure rather
        than a silent overwrite.
        """
        highest = self._session.scalar(
            select(RunEvent.sequence)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.sequence.desc())
            .limit(1)
            .with_for_update()
        )
        sequence = (highest or 0) + 1
        self._session.add(
            RunEvent(
                run_id=run_id,
                sequence=sequence,
                kind=kind,
                payload_json=json.dumps(payload),
                occurred_at=now,
            )
        )
        self._session.flush()
        return sequence

    def events(self, user_id: UUID, run_id: UUID, *, after: int = 0) -> list[EventRecord]:
        """This run's events in order, optionally only those after a sequence.

        Owner-scoped through the run, so a stranger holding a run identifier reads nothing
        — the identifier is the only thing they would need otherwise.
        """
        rows = self._session.scalars(
            select(RunEvent)
            .join(Run, Run.id == RunEvent.run_id)
            .where(
                Run.user_id == user_id,
                RunEvent.run_id == run_id,
                RunEvent.sequence > after,
            )
            .order_by(RunEvent.sequence)
        ).all()
        return [
            EventRecord(
                sequence=row.sequence,
                kind=row.kind,
                payload=json.loads(row.payload_json),
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]

    def _row(self, user_id: UUID, run_id: UUID) -> Run | None:
        return self._session.scalar(select(Run).where(Run.id == run_id, Run.user_id == user_id))
