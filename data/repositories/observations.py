"""Persistence for observations — a set of photos submitted at one point in time.

An observation has no owner column of its own: it reaches one through the plant it
belongs to, so every query here joins ``plants`` and filters on that owner. Denormalising
``user_id` onto the child would create a second, independently-wrong answer to the
question of who owns it.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import Observation, Plant
from data.repositories._ownership import require_plant

ObservationKind = Literal["initial", "recheck"]


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    id: UUID
    plant_id: UUID
    kind: ObservationKind
    photo_refs: list[str]
    user_notes: str | None
    created_at: datetime


def _to_record(row: Observation) -> ObservationRecord:
    return ObservationRecord(
        id=row.id,
        plant_id=row.plant_id,
        kind=row.kind,  # type: ignore[arg-type]
        photo_refs=json.loads(row.photo_refs),
        user_notes=row.user_notes,
        created_at=row.created_at,
    )


class ObservationRepository:
    """Reads and writes the ``observations`` table.

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
        plant_id: UUID,
        kind: ObservationKind,
        photo_refs: list[str],
        user_notes: str | None,
        now: datetime,
    ) -> UUID:
        """Record an observation against a plant this owner holds.

        The owner check is not decoration: without it, a caller could attach an
        observation — and through it a diagnosis — to somebody else's plant.
        """
        require_plant(self._session, user_id, plant_id)
        observation = Observation(
            plant_id=plant_id,
            kind=kind,
            photo_refs=json.dumps(photo_refs),
            user_notes=user_notes,
            created_at=now,
        )
        self._session.add(observation)
        self._session.flush()
        return observation.id

    def get(self, user_id: UUID, observation_id: UUID) -> ObservationRecord | None:
        row = self._session.scalar(
            select(Observation)
            .join(Plant, Observation.plant_id == Plant.id)
            .where(Observation.id == observation_id, Plant.user_id == user_id)
        )
        return _to_record(row) if row else None

    def list_for_plant(self, user_id: UUID, plant_id: UUID) -> list[ObservationRecord]:
        """Return every observation for a plant, oldest first.

        Ordered by time rather than by identifier. UUIDv7 does sort chronologically, but
        only to the millisecond — two observations written in the same millisecond would
        order arbitrarily, and the timeline this feeds is about sequence.
        """
        rows = self._session.scalars(
            select(Observation)
            .join(Plant, Observation.plant_id == Plant.id)
            .where(Observation.plant_id == plant_id, Plant.user_id == user_id)
            .order_by(Observation.created_at.asc(), Observation.id.asc())
        ).all()
        return [_to_record(r) for r in rows]
