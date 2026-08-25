"""Persistence for plants.

Every method takes ``user_id`` first, and every query filters on it. That is not a
convention this module follows carefully — it is the signature, so a caller cannot
reach another owner's plant without inventing an owner to do it with. The alternative,
trusting each method to remember its ``WHERE``, makes one omission a cross-tenant leak
across eight tables.

A plant belonging to somebody else is reported as absent rather than forbidden: a
refusal would confirm the row exists.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import Plant
from data.repositories.errors import RecordNotFoundError

LocationKind = Literal["indoor", "outdoor"]


@dataclass(frozen=True, slots=True)
class PlantRecord:
    id: UUID
    name: str
    species: str | None
    species_confidence: float | None
    location_kind: LocationKind
    location_text: str | None
    photo_ref: str | None
    created_at: datetime


def _to_record(row: Plant) -> PlantRecord:
    return PlantRecord(
        id=row.id,
        name=row.name,
        species=row.species,
        species_confidence=row.species_confidence,
        location_kind=row.location_kind,  # type: ignore[arg-type]
        location_text=row.location_text,
        photo_ref=row.photo_ref,
        created_at=row.created_at,
    )


class PlantRepository:
    """Reads and writes the ``plants`` table.

    Write methods do not commit; the caller groups writes with ``data.engine.transaction``.
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
        name: str,
        species: str | None,
        species_confidence: float | None,
        location_kind: LocationKind,
        location_text: str | None,
        photo_ref: str | None,
        now: datetime,
    ) -> UUID:
        plant = Plant(
            user_id=user_id,
            name=name,
            species=species,
            species_confidence=species_confidence,
            location_kind=location_kind,
            location_text=location_text,
            photo_ref=photo_ref,
            created_at=now,
        )
        self._session.add(plant)
        self._session.flush()
        return plant.id

    def get(self, user_id: UUID, plant_id: UUID) -> PlantRecord | None:
        row = self._session.scalar(
            select(Plant).where(Plant.id == plant_id, Plant.user_id == user_id)
        )
        return _to_record(row) if row else None

    def list_all(self, user_id: UUID) -> list[PlantRecord]:
        """Return the owner's plants, newest first."""
        rows = self._session.scalars(
            select(Plant)
            .where(Plant.user_id == user_id)
            .order_by(Plant.created_at.desc(), Plant.id.desc())
        ).all()
        return [_to_record(r) for r in rows]

    def delete(self, user_id: UUID, plant_id: UUID) -> None:
        self._session.delete(self._owned(user_id, plant_id))

    def rename(self, user_id: UUID, plant_id: UUID, *, name: str) -> None:
        """Give a plant a new display name.

        Separate from ``update_species``: the name is what the owner calls the plant
        and the species is what it is, and confirming one must not overwrite the
        other.
        """
        self._owned(user_id, plant_id).name = name

    def update_species(
        self, user_id: UUID, plant_id: UUID, *, species: str, species_confidence: float | None
    ) -> None:
        plant = self._owned(user_id, plant_id)
        plant.species = species
        plant.species_confidence = species_confidence

    def _owned(self, user_id: UUID, plant_id: UUID) -> Plant:
        """The plant, or ``RecordNotFoundError`` if it is absent or not this owner's.

        Writes go through here rather than through a filtered UPDATE so that "changed
        nothing" and "changed something" are distinguishable to the caller.
        """
        plant = self._session.scalar(
            select(Plant).where(Plant.id == plant_id, Plant.user_id == user_id)
        )
        if plant is None:
            raise RecordNotFoundError(f"no plant {plant_id} for this owner")
        return plant
