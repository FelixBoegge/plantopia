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

from agent.schemas import ContagionAssessment, Differential, Passage, WeatherSummary
from data.models import Diagnosis, Observation, Plant
from data.repositories._ownership import require_plant


@dataclass(frozen=True, slots=True)
class DiagnosisSpend:
    """What every diagnosis on an account has cost, summed.

    Cost and tokens are counted independently, the same way a single ``DiagnosisRecord``
    carries them: a diagnosis can have one without the other — a failed run records no
    cost, and neither is set on anything made before either was kept — so ``costed`` and
    ``tokened`` are not always equal to ``diagnosis_count``. ``None`` rather than ``0``
    when nothing at all was measured, for the reason `cost_usd` is nullable everywhere
    else in this codebase: zero would claim the account was measured and free.
    """

    diagnosis_count: int
    cost_usd: float | None
    costed_diagnosis_count: int
    token_usage: dict[str, int] | None
    tokened_diagnosis_count: int


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

    # Which method produced the species this diagnosis was reasoned from, and whether a
    # person picked it. ``None`` means unknown rather than none: a diagnosis written before
    # provenance was recorded cannot say, and claiming otherwise would put invented data in
    # the field that exists to attribute failures.
    species_method: str | None = None
    species_confirmed: bool = False

    # How this compared with the diagnosis before it: improving, static, worsening or
    # new_problem. ``None`` on a first diagnosis, which has nothing to compare against.
    progress_verdict: str | None = None

    # The weather this diagnosis was reasoned against, read from its observation.
    #
    # Carried here rather than left for a caller to fetch separately, because "why did it
    # say frost damage?" is a question about the diagnosis, and an answer that needs a
    # second request is one most callers will not make.
    #
    # ``None`` means no weather was recorded — an indoor plant, a failed lookup, or a
    # diagnosis made before the series was kept. Different from an empty window, which
    # would claim the weather was looked up and found to be nothing at all.
    weather: WeatherSummary | None = None


def _to_record(row: Diagnosis, weather_json: str | None = None) -> DiagnosisRecord:
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
        species_method=row.species_method,
        species_confirmed=bool(row.species_confirmed),
        progress_verdict=row.progress_verdict,
        weather=(WeatherSummary.model_validate_json(weather_json) if weather_json else None),
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
        species_method: str | None = None,
        species_confirmed: bool = False,
        progress_verdict: str | None = None,
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
            species_method=species_method,
            species_confirmed=species_confirmed,
            progress_verdict=progress_verdict,
        )
        self._session.add(diagnosis)
        self._session.flush()
        return diagnosis.id

    def get(self, user_id: UUID, diagnosis_id: UUID) -> DiagnosisRecord | None:
        row = self._session.execute(
            self._owned(user_id).where(Diagnosis.id == diagnosis_id)
        ).first()
        return _to_record(*row) if row else None

    def latest_for_plant(self, user_id: UUID, plant_id: UUID) -> DiagnosisRecord | None:
        row = self._session.execute(
            self._owned(user_id)
            .where(Diagnosis.plant_id == plant_id)
            .order_by(Diagnosis.created_at.desc(), Diagnosis.id.desc())
            .limit(1)
        ).first()
        return _to_record(*row) if row else None

    def list_for_plant(self, user_id: UUID, plant_id: UUID) -> list[DiagnosisRecord]:
        """Return every diagnosis for a plant, newest first."""
        rows = self._session.execute(
            self._owned(user_id)
            .where(Diagnosis.plant_id == plant_id)
            .order_by(Diagnosis.created_at.desc(), Diagnosis.id.desc())
        ).all()
        return [_to_record(*row) for row in rows]

    def total_spend(self, user_id: UUID) -> DiagnosisSpend:
        """Every diagnosis this owner has, across every plant, summed.

        Selects only the two columns this needs rather than the whole row: the account
        page has no use for a differential or a passage list, and those are the columns
        with real weight on them.

        Tokens are summed in Python rather than by the database: ``token_usage_json`` is
        a JSON blob, not three integer columns, so there is nothing for SQL to ``sum()``
        without unpacking it first — and the number of diagnoses one account has is
        nowhere near where that would start to matter.
        """
        rows = self._session.execute(
            select(Diagnosis.cost_usd, Diagnosis.token_usage_json)
            .join(Plant, Diagnosis.plant_id == Plant.id)
            .where(Plant.user_id == user_id)
        ).all()

        costs = [cost for cost, _ in rows if cost is not None]
        usages = [json.loads(usage) for _, usage in rows if usage is not None]

        return DiagnosisSpend(
            diagnosis_count=len(rows),
            cost_usd=sum(costs) if costs else None,
            costed_diagnosis_count=len(costs),
            token_usage=(
                {
                    "prompt_tokens": sum(u["prompt_tokens"] for u in usages),
                    "completion_tokens": sum(u["completion_tokens"] for u in usages),
                    "total_tokens": sum(u["total_tokens"] for u in usages),
                }
                if usages
                else None
            ),
            tokened_diagnosis_count=len(usages),
        )

    @staticmethod
    def _owned(user_id: UUID):
        """Every read starts here, so none of them can forget the join.

        Selects the observation's weather alongside the diagnosis. A second query per
        diagnosis would be an N+1 on the plant page, which lists every diagnosis a plant
        has; one join costs nothing and cannot be forgotten at a call site.
        """
        return (
            select(Diagnosis, Observation.weather_json)
            .join(Plant, Diagnosis.plant_id == Plant.id)
            .join(Observation, Diagnosis.observation_id == Observation.id)
            .where(Plant.user_id == user_id)
        )
