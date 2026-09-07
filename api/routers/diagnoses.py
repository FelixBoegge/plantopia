"""One diagnosis, by its identifier."""

from uuid import UUID

from fastapi import APIRouter

from api import converters
from api.dependencies import OwnerDep, PlantServiceDep, RunServiceDep
from api.schemas import ActivityStepOut, DiagnosisDetailOut
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
        diagnosis=converters.diagnosis(record, sources=service.sources_for(record)),
        roadmap_steps=[converters.roadmap_step(step) for step in steps],
    )


@router.get("/{diagnosis_id}/activity", response_model=list[ActivityStepOut])
def get_activity(
    diagnosis_id: UUID, service: PlantServiceDep, runs: RunServiceDep, owner: OwnerDep
) -> list[ActivityStepOut]:
    """What the run that produced this diagnosis did.

    Its own endpoint rather than a field on the diagnosis. `DiagnosisDetailOut` carries the
    diagnosis and its roadmap together because both are read on every screen showing either;
    this is not one of those — it is a panel somebody opens, and folding it in would make
    every diagnosis fetch carry a payload most callers ignore.

    An empty list is a real answer. A diagnosis reached before any of this was recorded has
    no activity, and that is different from a diagnosis nobody owns, which is a 404 here as
    it is everywhere else.
    """
    if service.get_diagnosis(diagnosis_id) is None:
        raise RecordNotFoundError(f"no diagnosis {diagnosis_id}")

    return [
        ActivityStepOut(
            sequence=event.sequence,
            step=event.payload["step"],
            description=event.payload["description"],
            calls=event.payload.get("calls"),
            duration_ms=event.payload.get("duration_ms"),
            occurred_at=event.occurred_at,
        )
        for event in runs.activity(diagnosis_id)
    ]
