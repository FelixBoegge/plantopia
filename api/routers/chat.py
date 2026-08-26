"""Conversation about one plant."""

import asyncio
import json
import logging
from functools import partial
from uuid import UUID

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from api import converters
from api.dependencies import ChatServiceDep, OwnerDep, SettingsDep
from api.schemas import ChatReplyOut, MessageOut, SendMessageIn
from data.repositories.errors import RecordNotFoundError
from runs import steps
from services.chat_events import ChatEvents

logger = logging.getLogger(__name__)

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

    One request, one answer — ten to thirty seconds of model work, and nothing to look at
    while it happens. `POST .../messages/stream` is the same call with the agent's progress
    visible; this one remains because the evaluation harness and every non-interactive
    caller want a reply rather than fragments to reassemble.
    """
    if service.get_plant(plant_id) is None:
        raise RecordNotFoundError(f"no plant {plant_id}")
    turn = service.send(plant_id, body.content)
    return ChatReplyOut(reply=turn.reply, escalated=turn.escalated)


@router.post("/stream")
async def stream_message(
    plant_id: UUID,
    body: SendMessageIn,
    service: ChatServiceDep,
    settings: SettingsDep,
    owner: OwnerDep,
):
    """Ask the agent about this plant and watch it answer.

    Same transcript as the single-request form, because it is the same call underneath —
    this only watches. The lookups the agent performs arrive as they happen, so consulting
    the corpus and then the web is visible rather than several seconds of silence.

    **The reply is recorded whether or not anybody is still listening.** The work runs to
    completion on its own thread, so a dropped connection costs a view of the answer rather
    than the answer; it is in the transcript either way.
    """
    if service.get_plant(plant_id) is None:
        raise RecordNotFoundError(f"no plant {plant_id}")

    events = ChatEvents()
    reply = asyncio.get_running_loop().run_in_executor(
        None, partial(_answer, service, plant_id, body.content, events)
    )
    return EventSourceResponse(_chat_events(events, reply), ping=settings.run_keepalive_seconds)


def _answer(service, plant_id: UUID, content: str, events: ChatEvents):
    """Produce the reply, and say so however it goes.

    ``finish`` in a ``finally``: a reader waiting on the next event would otherwise wait out
    its timeout on a turn that has already failed.
    """
    try:
        return service.send(plant_id, content, callbacks=[events])
    finally:
        events.finish()


async def _chat_events(events: ChatEvents, reply):
    """What the agent did, then what it said."""
    while True:
        event = await asyncio.to_thread(events.next, 0.2)
        if event is None:
            if reply.done():
                break
            continue
        kind, payload = event
        yield {"event": kind, "data": json.dumps(payload)}

    try:
        turn = await reply
    except Exception:
        logger.exception("a streamed chat turn failed")
        yield {
            "event": steps.FAILED,
            "data": json.dumps({"detail": "The reply could not be produced. Try again."}),
        }
        return

    yield {
        "event": steps.COMPLETED,
        "data": json.dumps({"reply": turn.reply, "escalated": turn.escalated}),
    }
