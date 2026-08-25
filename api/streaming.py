"""Turning a run's events into a stream a browser can hold open.

The shape of this is fixed by something the spike found: the graph's own generator *ends* at
the interrupt. So this never touches a graph. It replays what is stored, then follows the
bus, and the pause between a run's two halves is simply a gap between two publishes.

Three orderings matter here, and each of them is a bug if reversed:

1. **Subscribe before replaying.** An event published between the replay finishing and the
   subscription starting would be lost — and it is the interesting one, because it is the
   event that happened while the client was connecting.
2. **Discard what the replay already covered.** Subscribing first means the first live
   events may duplicate the tail of the replay. The sequence number is what settles it.
3. **Let go of the database before streaming.** A stream lives for minutes. Holding the
   request's session open for all of it would tie up a pooled connection per watcher, on
   top of one per running diagnosis.

The bus hands events over on the *worker's* thread, so they are hopped onto this loop with
``call_soon_threadsafe`` rather than read from a blocking queue. A thread per watcher would
be a thread doing nothing but waiting, and — measured, not assumed — it starves the
keep-alive task badly enough that an idle stream sends nothing at all.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from data.repositories.runs import EventRecord
from runs import steps
from runs.bus import SUBSCRIBER_BACKLOG, EventBus, Subscription

logger = logging.getLogger(__name__)

# Kinds after which there will never be another event for that run.
TERMINAL_KINDS = frozenset({steps.COMPLETED, steps.FAILED, steps.CANCELLED})

# How long a read waits before going back round the loop to send a keep-alive and check
# whether the client is still there. Short relative to the keep-alive interval so a
# disconnect is noticed promptly rather than one interval late.
POLL_SECONDS = 1.0


def _rendered(sequence: int, kind: str, payload: dict) -> dict:
    """One event in the shape ``EventSourceResponse`` expects.

    ``id`` is the sequence, which is what a browser echoes back as ``Last-Event-ID`` on a
    reconnect — the whole replay mechanism rests on it being here.
    """
    return {"id": str(sequence), "event": kind, "data": json.dumps(payload)}


def last_seen(header: str | None) -> int:
    """The sequence a reconnecting client says it already has.

    A header that is missing, empty or not a number means "from the beginning". Malformed
    is not an error: the value comes from a browser replaying whatever it last saw, and the
    conservative reading of nonsense is to send everything.
    """
    try:
        return max(0, int(header or 0))
    except (TypeError, ValueError):
        return 0


async def stream_run(
    *,
    request: Request,
    run_id: UUID,
    bus: EventBus,
    replay,
    after: int,
    keepalive_seconds: int,
) -> EventSourceResponse:
    """A live view of one run.

    ``replay`` is a callable returning the events already stored after a sequence. It is
    passed in rather than a repository so that this module never holds one — see the third
    ordering in the module docstring.
    """
    loop = asyncio.get_running_loop()
    incoming: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_BACKLOG)

    def _arrived(event) -> None:
        """Called on the worker's thread. Must not block and must not raise."""
        loop.call_soon_threadsafe(_offer, incoming, event)

    def _ended() -> None:
        loop.call_soon_threadsafe(_offer, incoming, None)

    subscription = bus.subscribe(run_id, on_event=_arrived, on_close=_ended)
    try:
        stored: list[EventRecord] = await run_in_threadpool(replay, after)
    except Exception:
        bus.unsubscribe(subscription)
        raise

    return EventSourceResponse(
        _events(request, subscription, bus, incoming, stored, after),
        ping=keepalive_seconds,
    )


def _offer(queue: asyncio.Queue, item) -> None:
    """Put something on the queue, or drop it.

    Dropping is safe: everything published was persisted first, and a client that misses
    one reconnects and replays. Blocking would not be safe — this runs on the loop, and a
    full queue means a reader that has stopped reading.
    """
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        logger.warning("dropped a streamed event: the client is not keeping up")


async def _events(
    request: Request,
    subscription: Subscription,
    bus: EventBus,
    incoming: asyncio.Queue,
    stored: list[EventRecord],
    after: int,
) -> AsyncIterator[dict]:
    """Everything already recorded, then everything that happens next."""
    highest = after
    try:
        for event in stored:
            highest = max(highest, event.sequence)
            yield _rendered(event.sequence, event.kind, event.payload)
            if event.kind in TERMINAL_KINDS:
                # The run finished before anybody watched. Nothing more is coming, so the
                # stream closes rather than waiting for an event that will never arrive.
                return

        while True:
            try:
                event = await asyncio.wait_for(incoming.get(), timeout=POLL_SECONDS)
            except TimeoutError:
                # Nothing happened. Going round again is what lets the keep-alive task run
                # and what notices a client that has gone away.
                if await request.is_disconnected():
                    return
                continue

            if event is None:
                return  # the run ended

            if event.sequence <= highest:
                # Already sent during the replay. Subscribing first is what makes this
                # possible, and is worth the duplicate.
                continue

            highest = event.sequence
            yield _rendered(event.sequence, event.kind, event.payload)
            if event.kind in TERMINAL_KINDS:
                return
    finally:
        bus.unsubscribe(subscription)
