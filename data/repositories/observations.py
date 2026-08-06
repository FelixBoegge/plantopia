"""Persistence for observations — a set of photos submitted at one point in time."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ObservationKind = Literal["initial", "recheck"]


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    id: int
    plant_id: int
    kind: ObservationKind
    photo_refs: list[str]
    user_notes: str | None
    created_at: datetime


def _to_record(row: sqlite3.Row) -> ObservationRecord:
    return ObservationRecord(
        id=row["id"],
        plant_id=row["plant_id"],
        kind=row["kind"],
        photo_refs=json.loads(row["photo_refs"]),
        user_notes=row["user_notes"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class ObservationRepository:
    """Reads and writes the ``observations`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        *,
        plant_id: int,
        kind: ObservationKind,
        photo_refs: list[str],
        user_notes: str | None,
        now: datetime,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO observations (plant_id, kind, photo_refs, user_notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (plant_id, kind, json.dumps(photo_refs), user_notes, now.isoformat()),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get(self, observation_id: int) -> ObservationRecord | None:
        row = self._conn.execute(
            "SELECT * FROM observations WHERE id = ?", (observation_id,)
        ).fetchone()
        return _to_record(row) if row else None

    def list_for_plant(self, plant_id: int) -> list[ObservationRecord]:
        """Return every observation for a plant, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM observations WHERE plant_id = ? ORDER BY id ASC", (plant_id,)
        ).fetchall()
        return [_to_record(r) for r in rows]
