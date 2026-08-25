"""Conversation about one plant."""

from uuid import UUID

from fastapi import APIRouter

from api import converters
from api.dependencies import ChatServiceDep, OwnerDep
from api.schemas import ChatReplyOut, MessageOut, SendMessageIn
from data.repositories.errors import RecordNotFoundError

router = APIRouter(prefix="/plants/{plant_id}/messages", tags=["chat"])


@router.get("", response_model=list[MessageOut])
def list_messages(plant_id: UUID, service: ChatServiceDep, owner: OwnerDep) -> list[MessageOut]:
    """The transcript, oldest first."""
    if service.get_plant(plant_id) is None:
        raise RecordNotFoundError(f"no plant {plant_id}")
    return [converters.message(record) for record in service.history(plant_id)]


@router.post("", response_model=ChatReplyOut)
def send_message(
    plant_id: UUID, body: SendMessageIn, service: ChatServiceDep, owner: OwnerDep
) -> ChatReplyOut:
    """Ask the agent about this plant and return its reply.

    One request, one answer — ten to thirty seconds of model work. Streaming belongs with
    the change that introduces background runs, and it will change this endpoint's
    response mode rather than replace the handler.
    """
    if service.get_plant(plant_id) is None:
        raise RecordNotFoundError(f"no plant {plant_id}")
    turn = service.send(plant_id, body.content)
    return ChatReplyOut(reply=turn.reply, escalated=turn.escalated)
