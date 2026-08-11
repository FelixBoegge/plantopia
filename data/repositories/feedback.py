"""Persistence for treatment-outcome feedback."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

DidItHelp = Literal["yes", "no", "unclear", "too_early"]


@dataclass(frozen=True, slots=True)
class FeedbackRecord:
    id: int
    diagnosis_id: int
    rating: int | None
    did_it_help: DidItHelp | None
    free_text: str | None
    created_at: datetime


def _to_record(row: sqlite3.Row) -> FeedbackRecord:
    return FeedbackRecord(
        id=row["id"],
        diagnosis_id=row["diagnosis_id"],
        rating=row["rating"],
        did_it_help=row["did_it_help"],
        free_text=row["free_text"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class FeedbackRepository:
    """Reads and writes the ``feedback`` table.

    Write methods do not commit; the caller groups writes with ``data.db.transaction``.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, for callers that need to group writes."""
        return self._conn

    def create(
        self,
        *,
        diagnosis_id: int,
        rating: int | None,
        did_it_help: DidItHelp | None,
        free_text: str | None,
        now: datetime,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO feedback (diagnosis_id, rating, did_it_help, free_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (diagnosis_id, rating, did_it_help, free_text, now.isoformat()),
        )
        return int(cursor.lastrowid)

    def exists_for_diagnosis(self, diagnosis_id: int) -> bool:
        """Whether feedback has already been recorded for this diagnosis.

        The Plant detail page uses this to avoid re-prompting for feedback already
        given.
        """
        row = self._conn.execute(
            "SELECT 1 FROM feedback WHERE diagnosis_id = ? LIMIT 1", (diagnosis_id,)
        ).fetchone()
        return row is not None
