"""Persistence for chat transcripts."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from data.models import Message
from data.repositories._ownership import require_plant

MessageRole = Literal["user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: UUID
    plant_id: UUID
    role: MessageRole
    content: str
    tool_calls: list[dict] | None
    created_at: datetime


def _to_record(row: Message) -> MessageRecord:
    return MessageRecord(
        id=row.id,
        plant_id=row.plant_id,
        role=row.role,  # type: ignore[arg-type]
        content=row.content,
        tool_calls=json.loads(row.tool_calls_json) if row.tool_calls_json else None,
        created_at=row.created_at,
    )


class MessageRepository:
    """Reads and writes the ``messages`` table.

    Write methods do not commit; the caller groups writes with ``data.engine.transaction``.

    Messages carry ``user_id`` directly as well as reaching one through their plant.
    A conversation is with the owner rather than about the plant, and deleting an
    account has to reach every message the person wrote whatever became of the plants.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """The underlying session, for callers that need to group writes."""
        return self._session

    def create(
        self,
        user_id: UUID,
        *,
        plant_id: UUID,
        role: MessageRole,
        content: str,
        tool_calls: list[dict] | None,
        now: datetime,
    ) -> UUID:
        require_plant(self._session, user_id, plant_id)
        row = Message(
            plant_id=plant_id,
            user_id=user_id,
            role=role,
            content=content,
            tool_calls_json=json.dumps(tool_calls) if tool_calls is not None else None,
            created_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def list_for_plant(self, user_id: UUID, plant_id: UUID) -> list[MessageRecord]:
        """Return every message for a plant, oldest first.

        Ordered by time, then by identifier as a tie-break. The SQLite version ordered
        by ``id`` alone, which an autoincrementing integer made chronological for free;
        UUIDv7 only orders to the millisecond, and a chat turn plus its tool messages
        can easily share one.
        """
        rows = self._session.scalars(
            select(Message)
            .where(Message.plant_id == plant_id, Message.user_id == user_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        ).all()
        return [_to_record(r) for r in rows]

    def list_for_plant_after(
        self, user_id: UUID, plant_id: UUID, *, after: tuple[datetime, UUID] | None
    ) -> list[MessageRecord]:
        """Messages after a position, oldest first; all of them when it is ``None``.

        The position is ``(created_at, id)``, compared as a row value so it agrees
        exactly with the ordering below. Comparing timestamps alone would drop every
        message that shares a ``created_at`` with the cursor — which is not a rare
        edge: a batch written in one transaction shares a single clock reading.

        Profile extraction used to filter with ``m.id > cursor or 0`` — an integer
        comparison against a sentinel no UUID can have. Asking the database for the
        window keeps that logic in one place and removes the sentinel entirely.
        """
        statement = select(Message).where(Message.plant_id == plant_id, Message.user_id == user_id)
        if after is not None:
            statement = statement.where(tuple_(Message.created_at, Message.id) > after)
        rows = self._session.scalars(
            statement.order_by(Message.created_at.asc(), Message.id.asc())
        ).all()
        return [_to_record(r) for r in rows]
