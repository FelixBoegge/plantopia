"""One diagnosis, by its identifier."""

from uuid import UUID

from fastapi import APIRouter

from api import converters
from api.dependencies import OwnerDep, PlantServiceDep
from api.schemas import DiagnosisDetailOut
from data.repositories.errors import RecordNotFoundError

router = APIRouter(prefix="/diagnoses", tags=["diagnoses"])


@router.get("/{diagnosis_id}", response_model=DiagnosisDetailOut)
def get_diagnosis(
    diagnosis_id: UUID, service: PlantServiceDep, owner: OwnerDep
) -> DiagnosisDetailOut:
    """A diagnosis and the plan it produced.

    Reachable directly so that a link to a result works, and so that the identifier a run
    reports on completion resolves to something. Another owner's is 404, like everything
    else here — never 403.
    """
    found = service.get_diagnosis(diagnosis_id)
    if found is None:
        raise RecordNotFoundError(f"no diagnosis {diagnosis_id}")

    record, steps = found
    return DiagnosisDetailOut(
        diagnosis=converters.diagnosis(record),
        roadmap_steps=[converters.roadmap_step(step) for step in steps],
    )
