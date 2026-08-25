"""Persistence for diagnoses.

The full differential is stored as JSON; the leading candidate is also written to
denormalised columns so the plant list can render health badges without
deserialising every diagnosis.

Like observations, a diagnosis reaches its owner through its plant.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.schemas import ContagionAssessment, Differential, Passage
from data.models import Diagnosis, Plant
from data.repositories._ownership import require_plant


@dataclass(frozen=True, slots=True)
class DiagnosisRecord:
    id: UUID
    observation_id: UUID
    plant_id: UUID
    differential: Differential
    contagion: ContagionAssessment | None
    retrieved: list[Passage]
    model: str
    token_usage: dict[str, int] | None
    cost_usd: float | None
    created_at: datetime


def _to_record(row: Diagnosis) -> DiagnosisRecord:
    return DiagnosisRecord(
        id=row.id,
        observation_id=row.observation_id,
        plant_id=row.plant_id,
        differential=Differential.model_validate_json(row.differential_json),
        contagion=(
            ContagionAssessment.model_validate_json(row.contagion_json)
            if row.contagion_json
            else None
        ),
        retrieved=[Passage.model_validate(p) for p in json.loads(row.retrieved_refs_json)],
        model=row.model,
        token_usage=json.loads(row.token_usage_json) if row.token_usage_json else None,
        cost_usd=row.cost_usd,
        created_at=row.created_at,
    )


class DiagnosisRepository:
    """Reads and writes the ``diagnoses`` table.

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
        observation_id: UUID,
        plant_id: UUID,
        differential: Differential,
        contagion: ContagionAssessment | None,
        retrieved: list[Passage],
        model: str,
        now: datetime,
        cost_usd: float | None = None,
        token_usage: dict[str, int] | None = None,
    ) -> UUID:
        require_plant(self._session, user_id, plant_id)
        primary = differential.primary
        diagnosis = Diagnosis(
            observation_id=observation_id,
            plant_id=plant_id,
            differential_json=differential.model_dump_json(),
            primary_candidate=primary.disorder_id if primary else None,
            primary_confidence=primary.probability if primary else None,
            severity=primary.severity.value if primary else None,
            contagion_json=contagion.model_dump_json() if contagion else None,
            retrieved_refs_json=json.dumps([p.model_dump() for p in retrieved]),
            model=model,
            token_usage_json=json.dumps(token_usage) if token_usage else None,
            cost_usd=cost_usd,
            created_at=now,
        )
        self._session.add(diagnosis)
        self._session.flush()
        return diagnosis.id

    def get(self, user_id: UUID, diagnosis_id: UUID) -> DiagnosisRecord | None:
        row = self._session.scalar(self._owned(user_id).where(Diagnosis.id == diagnosis_id))
        return _to_record(row) if row else None

    def latest_for_plant(self, user_id: UUID, plant_id: UUID) -> DiagnosisRecord | None:
        row = self._session.scalar(
            self._owned(user_id)
            .where(Diagnosis.plant_id == plant_id)
            .order_by(Diagnosis.created_at.desc(), Diagnosis.id.desc())
            .limit(1)
        )
        return _to_record(row) if row else None

    def list_for_plant(self, user_id: UUID, plant_id: UUID) -> list[DiagnosisRecord]:
        """Return every diagnosis for a plant, newest first."""
        rows = self._session.scalars(
            self._owned(user_id)
            .where(Diagnosis.plant_id == plant_id)
            .order_by(Diagnosis.created_at.desc(), Diagnosis.id.desc())
        ).all()
        return [_to_record(r) for r in rows]

    @staticmethod
    def _owned(user_id: UUID):
        """Every read starts here, so none of them can forget the join."""
        return (
            select(Diagnosis)
            .join(Plant, Diagnosis.plant_id == Plant.id)
            .where(Plant.user_id == user_id)
        )
