"""Recording what the owner did about a diagnosis."""

from uuid import UUID

from fastapi import APIRouter, status

from api.dependencies import OwnerDep, PlantServiceDep
from api.schemas import FeedbackIn, MarkStepIn

router = APIRouter(tags=["care"])


@router.patch("/roadmap-steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
def mark_step(step_id: UUID, body: MarkStepIn, service: PlantServiceDep, owner: OwnerDep) -> None:
    """Tick a step, skip it, or reopen it.

    Reopening clears the completion time: a step marked done and then reopened has not
    been done, and a timestamp saying otherwise would be a lie the timeline repeats.

    Returns no body. Handing back the updated step would need a service method that reads
    one — and a client that marks a step is about to refetch the plant anyway, because its
    outstanding-step count has just changed.
    """
    service.mark_roadmap_step(step_id, status=body.status)


@router.post(
    "/diagnoses/{diagnosis_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
def submit_feedback(
    diagnosis_id: UUID, body: FeedbackIn, service: PlantServiceDep, owner: OwnerDep
) -> None:
    """Record how a treatment went."""
    service.submit_feedback(
        diagnosis_id=diagnosis_id,
        rating=body.rating,
        did_it_help=body.did_it_help,
        free_text=body.free_text,
    )
