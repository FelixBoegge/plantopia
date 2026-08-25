"""Ownership checks shared by the repositories whose tables have no owner column.

Observations, diagnoses, roadmap steps, feedback and messages all reach an owner through
the plant they belong to. Reads express that as a join; writes need it as a guard,
because attaching a child row to somebody else's plant is how a record ends up in a
timeline its owner never asked for.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import Diagnosis, Plant
from data.repositories.errors import RecordNotFoundError


def require_plant(session: Session, user_id: UUID, plant_id: UUID) -> None:
    """Raise unless this owner holds this plant."""
    held = session.scalar(select(Plant.id).where(Plant.id == plant_id, Plant.user_id == user_id))
    if held is None:
        raise RecordNotFoundError(f"no plant {plant_id} for this owner")


def require_diagnosis(session: Session, user_id: UUID, diagnosis_id: UUID) -> None:
    """Raise unless this owner holds the plant the diagnosis belongs to."""
    held = session.scalar(
        select(Diagnosis.id)
        .join(Plant, Diagnosis.plant_id == Plant.id)
        .where(Diagnosis.id == diagnosis_id, Plant.user_id == user_id)
    )
    if held is None:
        raise RecordNotFoundError(f"no diagnosis {diagnosis_id} for this owner")
