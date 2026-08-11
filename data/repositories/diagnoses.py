"""Persistence for diagnoses.

The full differential is stored as JSON; the leading candidate is also written to
denormalised columns so the plant list can render health badges without
deserialising every diagnosis.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from agent.schemas import ContagionAssessment, Differential, Passage


@dataclass(frozen=True, slots=True)
class DiagnosisRecord:
    id: int
    observation_id: int
    plant_id: int
    differential: Differential
    contagion: ContagionAssessment | None
    retrieved: list[Passage]
    model: str
    cost_usd: float | None
    created_at: datetime


def _to_record(row: sqlite3.Row) -> DiagnosisRecord:
    contagion_raw = row["contagion_json"]
    return DiagnosisRecord(
        id=row["id"],
        observation_id=row["observation_id"],
        plant_id=row["plant_id"],
        differential=Differential.model_validate_json(row["differential_json"]),
        contagion=ContagionAssessment.model_validate_json(contagion_raw) if contagion_raw else None,
        retrieved=[Passage.model_validate(p) for p in json.loads(row["retrieved_refs_json"])],
        model=row["model"],
        cost_usd=row["cost_usd"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class DiagnosisRepository:
    """Reads and writes the ``diagnoses`` table.

    Write methods do not commit; the caller groups writes with ``data.db.transaction``.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        *,
        observation_id: int,
        plant_id: int,
        differential: Differential,
        contagion: ContagionAssessment | None,
        retrieved: list[Passage],
        model: str,
        now: datetime,
        cost_usd: float | None = None,
        token_usage: dict[str, int] | None = None,
    ) -> int:
        primary = differential.primary
        cursor = self._conn.execute(
            """
            INSERT INTO diagnoses
                (observation_id, plant_id, differential_json, primary_candidate,
                 primary_confidence, severity, contagion_json, retrieved_refs_json,
                 model, token_usage_json, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                plant_id,
                differential.model_dump_json(),
                primary.disorder_id if primary else None,
                primary.probability if primary else None,
                primary.severity.value if primary else None,
                contagion.model_dump_json() if contagion else None,
                json.dumps([p.model_dump() for p in retrieved]),
                model,
                json.dumps(token_usage) if token_usage else None,
                cost_usd,
                now.isoformat(),
            ),
        )
        return int(cursor.lastrowid)

    def get(self, diagnosis_id: int) -> DiagnosisRecord | None:
        row = self._conn.execute("SELECT * FROM diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
        return _to_record(row) if row else None

    def latest_for_plant(self, plant_id: int) -> DiagnosisRecord | None:
        row = self._conn.execute(
            "SELECT * FROM diagnoses WHERE plant_id = ? ORDER BY id DESC LIMIT 1", (plant_id,)
        ).fetchone()
        return _to_record(row) if row else None

    def list_for_plant(self, plant_id: int) -> list[DiagnosisRecord]:
        """Return every diagnosis for a plant, newest first."""
        rows = self._conn.execute(
            "SELECT * FROM diagnoses WHERE plant_id = ? ORDER BY id DESC", (plant_id,)
        ).fetchall()
        return [_to_record(r) for r in rows]
