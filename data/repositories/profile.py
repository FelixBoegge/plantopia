"""Persistence for the learned user profile.

Facts are about the *owner*, not about any one plant — "waters on a schedule",
"lives in Berlin". Plant history is deliberately not stored here: the diagnoses
table already records it exactly and the chat agent already reads it, so a
paraphrase would be a second, contradictable source of truth (spec §1).

``user_profile.fact`` is UNIQUE, so confirming a known fact must go through
``upsert`` rather than a second insert.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

FactSource = Literal["inferred", "stated"]


@dataclass(frozen=True, slots=True)
class ProfileFact:
    """One stored belief about the owner."""

    fact: str
    source: FactSource
    confidence: float
    first_seen: datetime
    last_confirmed: datetime


def _to_record(row: sqlite3.Row) -> ProfileFact:
    return ProfileFact(
        fact=row["fact"],
        source=row["source"],
        confidence=row["confidence"],
        first_seen=datetime.fromisoformat(row["first_seen"]),
        last_confirmed=datetime.fromisoformat(row["last_confirmed"]),
    )


class ProfileRepository:
    """Reads and writes ``user_profile`` and ``profile_cursors``.

    Write methods do not commit; the caller groups writes with ``data.db.transaction``.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, for callers that need to group writes."""
        return self._conn

    def list_all(self) -> list[ProfileFact]:
        """Every fact, most confident first, then most recently confirmed."""
        rows = self._conn.execute(
            "SELECT * FROM user_profile ORDER BY confidence DESC, last_confirmed DESC"
        ).fetchall()
        return [_to_record(row) for row in rows]

    def upsert(self, *, fact: str, source: FactSource, confidence: float, now: datetime) -> None:
        """Insert a new fact, or confirm a known one.

        ``first_seen`` is preserved on confirmation — it records when the belief was
        first formed, which is what makes a long-held fact distinguishable from one
        observed once.
        """
        self._conn.execute(
            """
            INSERT INTO user_profile (fact, source, confidence, first_seen, last_confirmed)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fact) DO UPDATE SET
                confidence     = excluded.confidence,
                last_confirmed = excluded.last_confirmed
            """,
            (fact, source, confidence, now.isoformat(), now.isoformat()),
        )

    def supersede(self, fact: str) -> None:
        """Remove a contradicted fact. Silent when it is not there."""
        self._conn.execute("DELETE FROM user_profile WHERE fact = ?", (fact,))

    def cursor_for(self, plant_id: int) -> int | None:
        """The id of the last chat message profile extraction has read for this plant."""
        row = self._conn.execute(
            "SELECT last_message_id FROM profile_cursors WHERE plant_id = ?", (plant_id,)
        ).fetchone()
        return int(row["last_message_id"]) if row else None

    def set_cursor(self, *, plant_id: int, last_message_id: int) -> None:
        """Advance the cursor, creating it on first use."""
        self._conn.execute(
            """
            INSERT INTO profile_cursors (plant_id, last_message_id)
            VALUES (?, ?)
            ON CONFLICT(plant_id) DO UPDATE SET last_message_id = excluded.last_message_id
            """,
            (plant_id, last_message_id),
        )
