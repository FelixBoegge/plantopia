"""Persistence for roadmap steps.

``RoadmapStep.day_offset`` is relative to the diagnosis; this layer converts it to
an absolute due date using the caller's clock.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from agent.schemas import IPMTier, Roadmap

StepStatus = Literal["pending", "done", "skipped"]
_VALID_STATUSES: frozenset[str] = frozenset({"pending", "done", "skipped"})


@dataclass(frozen=True, slots=True)
class RoadmapStepRecord:
    id: int
    diagnosis_id: int
    plant_id: int
    ordinal: int
    action: str
    rationale: str
    success_signal: str
    tier: IPMTier
    due_date: datetime
    status: StepStatus
    completed_at: datetime | None


def _to_record(row: sqlite3.Row) -> RoadmapStepRecord:
    completed = row["completed_at"]
    return RoadmapStepRecord(
        id=row["id"],
        diagnosis_id=row["diagnosis_id"],
        plant_id=row["plant_id"],
        ordinal=row["ordinal"],
        action=row["action"],
        rationale=row["rationale"],
        success_signal=row["success_signal"],
        tier=IPMTier(row["tier"]),
        due_date=datetime.fromisoformat(row["due_date"]),
        status=row["status"],
        completed_at=datetime.fromisoformat(completed) if completed else None,
    )


class RoadmapRepository:
    """Reads and writes the ``roadmap_steps`` table.

    Write methods do not commit; the caller groups writes with ``data.db.transaction``.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, for callers that need to group writes."""
        return self._conn

    def create_from_roadmap(
        self,
        *,
        diagnosis_id: int,
        plant_id: int,
        roadmap: Roadmap,
        now: datetime,
    ) -> list[int]:
        """Insert every step, converting day offsets to absolute due dates."""
        created: list[int] = []
        for step in roadmap.steps:
            cursor = self._conn.execute(
                """
                INSERT INTO roadmap_steps
                    (diagnosis_id, plant_id, ordinal, action, rationale,
                     success_signal, tier, due_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    diagnosis_id,
                    plant_id,
                    step.ordinal,
                    step.action,
                    step.rationale,
                    step.success_signal,
                    int(step.tier),
                    (now + timedelta(days=step.day_offset)).isoformat(),
                ),
            )
            created.append(int(cursor.lastrowid))
        return created

    def list_for_plant(self, plant_id: int) -> list[RoadmapStepRecord]:
        """Return every step for a plant, newest diagnosis first, then by ordinal."""
        rows = self._conn.execute(
            """
            SELECT * FROM roadmap_steps
            WHERE plant_id = ?
            ORDER BY diagnosis_id DESC, ordinal ASC
            """,
            (plant_id,),
        ).fetchall()
        return [_to_record(r) for r in rows]

    def mark(self, step_id: int, *, status: StepStatus, now: datetime) -> None:
        """Set a step's status, recording completion time for terminal statuses.

        Does not commit. Callers own the transaction — wrap in
        ``data.db.transaction(...)`` (see ``agent/nodes/persist.py`` for the pattern).

        Raises:
            ValueError: if ``status`` is not a valid status, or ``step_id`` does not
                match any roadmap step.
        """
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"unknown status {status!r}; expected one of {sorted(_VALID_STATUSES)}"
            )

        completed_at = None if status == "pending" else now.isoformat()
        cursor = self._conn.execute(
            "UPDATE roadmap_steps SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed_at, step_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"no roadmap step with id {step_id}")

    def due_before(self, when: datetime) -> list[RoadmapStepRecord]:
        """Return pending steps due at or before ``when``, most overdue first."""
        rows = self._conn.execute(
            """
            SELECT * FROM roadmap_steps
            WHERE status = 'pending' AND due_date <= ?
            ORDER BY due_date ASC
            """,
            (when.isoformat(),),
        ).fetchall()
        return [_to_record(r) for r in rows]
