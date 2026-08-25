"""Persistence for roadmap steps.

``RoadmapStep.day_offset`` is relative to the diagnosis; this layer converts it to
an absolute due date using the caller's clock.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.schemas import IPMTier, Roadmap
from data.models import Diagnosis, Plant
from data.models import RoadmapStep as RoadmapStepRow
from data.repositories._ownership import require_plant
from data.repositories.errors import RecordNotFoundError

StepStatus = Literal["pending", "done", "skipped"]
_VALID_STATUSES: frozenset[str] = frozenset({"pending", "done", "skipped"})


@dataclass(frozen=True, slots=True)
class RoadmapStepRecord:
    id: UUID
    diagnosis_id: UUID
    plant_id: UUID
    ordinal: int
    action: str
    rationale: str
    success_signal: str
    tier: IPMTier
    due_date: datetime
    status: StepStatus
    completed_at: datetime | None


def _to_record(row: RoadmapStepRow) -> RoadmapStepRecord:
    return RoadmapStepRecord(
        id=row.id,
        diagnosis_id=row.diagnosis_id,
        plant_id=row.plant_id,
        ordinal=row.ordinal,
        action=row.action,
        rationale=row.rationale,
        success_signal=row.success_signal,
        tier=IPMTier(row.tier),
        due_date=row.due_date,
        status=row.status,  # type: ignore[arg-type]
        completed_at=row.completed_at,
    )


class RoadmapRepository:
    """Reads and writes the ``roadmap_steps`` table.

    Write methods do not commit; the caller groups writes with ``data.engine.transaction``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """The underlying session, for callers that need to group writes."""
        return self._session

    def create_from_roadmap(
        self,
        user_id: UUID,
        *,
        diagnosis_id: UUID,
        plant_id: UUID,
        roadmap: Roadmap,
        now: datetime,
    ) -> list[UUID]:
        """Insert every step, converting day offsets to absolute due dates."""
        require_plant(self._session, user_id, plant_id)
        created: list[UUID] = []
        for step in roadmap.steps:
            row = RoadmapStepRow(
                diagnosis_id=diagnosis_id,
                plant_id=plant_id,
                ordinal=step.ordinal,
                action=step.action,
                rationale=step.rationale,
                success_signal=step.success_signal,
                tier=int(step.tier),
                due_date=now + timedelta(days=step.day_offset),
                status="pending",
            )
            self._session.add(row)
            self._session.flush()
            created.append(row.id)
        return created

    def list_for_plant(self, user_id: UUID, plant_id: UUID) -> list[RoadmapStepRecord]:
        """Return every step for a plant, newest diagnosis first, then by ordinal.

        Ordered by the diagnosis's timestamp rather than by its identifier: the SQLite
        version leaned on ``diagnosis_id DESC`` being chronological, which an
        autoincrementing integer guaranteed and a UUID does not beyond the millisecond.
        """
        rows = self._session.scalars(
            select(RoadmapStepRow)
            .join(Plant, RoadmapStepRow.plant_id == Plant.id)
            .join(Diagnosis, RoadmapStepRow.diagnosis_id == Diagnosis.id)
            .where(RoadmapStepRow.plant_id == plant_id, Plant.user_id == user_id)
            .order_by(Diagnosis.created_at.desc(), RoadmapStepRow.ordinal.asc())
        ).all()
        return [_to_record(r) for r in rows]

    def mark(self, user_id: UUID, step_id: UUID, *, status: StepStatus, now: datetime) -> None:
        """Set a step's status, recording completion time for terminal statuses.

        Does not commit. Callers own the transaction — wrap in
        ``data.engine.transaction(...)`` (see ``agent/nodes/persist.py`` for the pattern).

        Raises:
            ValueError: if ``status`` is not a valid status.
            RecordNotFoundError: if the step does not exist or is not this owner's. M10
                recorded the version that silently no-opped; a step that belongs to
                somebody else has to fail the same way an absent one does.
        """
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"unknown status {status!r}; expected one of {sorted(_VALID_STATUSES)}"
            )

        row = self._session.scalar(
            select(RoadmapStepRow)
            .join(Plant, RoadmapStepRow.plant_id == Plant.id)
            .where(RoadmapStepRow.id == step_id, Plant.user_id == user_id)
        )
        if row is None:
            raise RecordNotFoundError(f"no roadmap step with id {step_id}")

        row.status = status
        row.completed_at = None if status == "pending" else now

    def due_before(self, user_id: UUID, when: datetime) -> list[RoadmapStepRecord]:
        """Return this owner's pending steps due at or before ``when``, most overdue first."""
        rows = self._session.scalars(
            select(RoadmapStepRow)
            .join(Plant, RoadmapStepRow.plant_id == Plant.id)
            .where(
                Plant.user_id == user_id,
                RoadmapStepRow.status == "pending",
                RoadmapStepRow.due_date <= when,
            )
            .order_by(RoadmapStepRow.due_date.asc())
        ).all()
        return [_to_record(r) for r in rows]
