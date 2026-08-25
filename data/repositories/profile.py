"""Persistence for the learned user profile.

Facts are about the *owner*, not about any one plant — "waters on a schedule",
"lives in Berlin". Plant history is deliberately not stored here: the diagnoses
table already records it exactly and the chat agent already reads it, so a
paraphrase would be a second, contradictable source of truth (spec §1).

Uniqueness is ``(user_id, fact)``, not ``fact``. The single-user constraint would have
made the second person who tends to overwater a conflict rather than a second row, so
``upsert`` conflicts only against the same owner's set.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from data.models import Message, ProfileCursor
from data.models import ProfileFact as ProfileFactRow
from data.repositories._ownership import require_plant

FactSource = Literal["inferred", "stated"]


@dataclass(frozen=True, slots=True)
class ProfileFact:
    """One stored belief about the owner."""

    fact: str
    source: FactSource
    confidence: float
    first_seen: datetime
    last_confirmed: datetime


def _to_record(row: ProfileFactRow) -> ProfileFact:
    return ProfileFact(
        fact=row.fact,
        source=row.source,  # type: ignore[arg-type]
        confidence=row.confidence,
        first_seen=row.first_seen,
        last_confirmed=row.last_confirmed,
    )


class ProfileRepository:
    """Reads and writes ``user_profile`` and ``profile_cursors``.

    Write methods do not commit; the caller groups writes with ``data.engine.transaction``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """The underlying session, for callers that need to group writes."""
        return self._session

    def list_all(self, user_id: UUID) -> list[ProfileFact]:
        """This owner's facts, most confident first, then most recently confirmed."""
        rows = self._session.scalars(
            select(ProfileFactRow)
            .where(ProfileFactRow.user_id == user_id)
            .order_by(ProfileFactRow.confidence.desc(), ProfileFactRow.last_confirmed.desc())
        ).all()
        return [_to_record(row) for row in rows]

    def upsert(
        self, user_id: UUID, *, fact: str, source: FactSource, confidence: float, now: datetime
    ) -> None:
        """Insert a new fact, or confirm one this owner already holds.

        ``first_seen`` is preserved on confirmation — it records when the belief was
        first formed, which is what makes a long-held fact distinguishable from one
        observed once.
        """
        statement = (
            insert(ProfileFactRow)
            .values(
                user_id=user_id,
                fact=fact,
                source=source,
                confidence=confidence,
                first_seen=now,
                last_confirmed=now,
            )
            .on_conflict_do_update(
                index_elements=[ProfileFactRow.user_id, ProfileFactRow.fact],
                set_={"confidence": confidence, "last_confirmed": now},
            )
        )
        self._session.execute(statement)

    def supersede(self, user_id: UUID, fact: str) -> None:
        """Remove a contradicted fact. Silent when it is not there.

        Silence is deliberate here, unlike the write methods that raise: superseding is
        driven by reconciliation deciding a belief no longer holds, and a belief the
        system never held is already in the desired state.
        """
        row = self._session.scalar(
            select(ProfileFactRow).where(
                ProfileFactRow.user_id == user_id, ProfileFactRow.fact == fact
            )
        )
        if row is not None:
            self._session.delete(row)

    def cursor_position(self, user_id: UUID, plant_id: UUID) -> tuple[datetime, UUID] | None:
        """Where profile extraction has read up to: a time *and* the message id.

        Both halves are needed. A timestamp alone cannot order messages written in the
        same transaction — they share one ``now()`` — so ``created_at > cursor`` would
        skip a whole batch that arrived alongside the one already read. The pair
        matches the ordering ``list_for_plant`` uses, so "everything after this point"
        means the same thing to both.
        """
        return self._session.execute(
            select(Message.created_at, Message.id)
            .join(ProfileCursor, ProfileCursor.last_message_id == Message.id)
            .where(ProfileCursor.plant_id == plant_id, Message.user_id == user_id)
        ).first()

    def set_cursor(self, user_id: UUID, *, plant_id: UUID, last_message_id: UUID) -> None:
        """Advance the cursor, creating it on first use."""
        require_plant(self._session, user_id, plant_id)
        statement = (
            insert(ProfileCursor)
            .values(plant_id=plant_id, last_message_id=last_message_id)
            .on_conflict_do_update(
                index_elements=[ProfileCursor.plant_id],
                set_={"last_message_id": last_message_id},
            )
        )
        self._session.execute(statement)
