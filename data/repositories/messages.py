"""Persistence for chat transcripts."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

MessageRole = Literal["user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: int
    plant_id: int
    role: MessageRole
    content: str
    tool_calls: list[dict] | None
    created_at: datetime


def _to_record(row: sqlite3.Row) -> MessageRecord:
    raw = row["tool_calls_json"]
    return MessageRecord(
        id=row["id"],
        plant_id=row["plant_id"],
        role=row["role"],
        content=row["content"],
        tool_calls=json.loads(raw) if raw else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class MessageRepository:
    """Reads and writes the ``messages`` table.

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
        plant_id: int,
        role: MessageRole,
        content: str,
        tool_calls: list[dict] | None,
        now: datetime,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO messages (plant_id, role, content, tool_calls_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                plant_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls is not None else None,
                now.isoformat(),
            ),
        )
        return int(cursor.lastrowid)

    def list_for_plant(self, plant_id: int) -> list[MessageRecord]:
        """Return every message for a plant, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE plant_id = ? ORDER BY id ASC", (plant_id,)
        ).fetchall()
        return [_to_record(r) for r in rows]
