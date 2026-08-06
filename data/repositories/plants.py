"""Persistence for plants."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

LocationKind = Literal["indoor", "outdoor"]


@dataclass(frozen=True, slots=True)
class PlantRecord:
    id: int
    name: str
    species: str | None
    species_confidence: float | None
    location_kind: LocationKind
    location_text: str | None
    photo_ref: str | None
    created_at: datetime


def _to_record(row: sqlite3.Row) -> PlantRecord:
    return PlantRecord(
        id=row["id"],
        name=row["name"],
        species=row["species"],
        species_confidence=row["species_confidence"],
        location_kind=row["location_kind"],
        location_text=row["location_text"],
        photo_ref=row["photo_ref"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class PlantRepository:
    """Reads and writes the ``plants`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        *,
        name: str,
        species: str | None,
        species_confidence: float | None,
        location_kind: LocationKind,
        location_text: str | None,
        photo_ref: str | None,
        now: datetime,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO plants
                (name, species, species_confidence, location_kind,
                 location_text, photo_ref, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                species,
                species_confidence,
                location_kind,
                location_text,
                photo_ref,
                now.isoformat(),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get(self, plant_id: int) -> PlantRecord | None:
        row = self._conn.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
        return _to_record(row) if row else None

    def list_all(self) -> list[PlantRecord]:
        """Return every plant, newest first."""
        rows = self._conn.execute("SELECT * FROM plants ORDER BY id DESC").fetchall()
        return [_to_record(r) for r in rows]

    def delete(self, plant_id: int) -> None:
        self._conn.execute("DELETE FROM plants WHERE id = ?", (plant_id,))
        self._conn.commit()
