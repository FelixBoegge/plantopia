"""Where a run's events go once they are written.

**Persisted first, published here second.** Publishing first would mean a client can
receive an event the database does not have, and a reconnect that replays a shorter history
than the one already on screen. So this is a courier, not a record: everything it carries
already exists, and losing a delivery costs a client nothing it cannot get by reconnecting.

That is what lets publishing be non-blocking. A subscriber who has stopped reading — a
closed tab whose connection has not noticed yet — must never hold up the worker, so a full
subscriber queue drops rather than waits. The dropped event is still in the database, and
the reconnect that follows replays it.

**In-process, and that is the constraint on the deployment.** Two API processes and a
client connected to one sees nothing for a run progressing on the other. The port that
would fix it is the executor's, not this one; until then the deployment is one process, the
same way `M28` already requires for rate limiting.
"""

import logging
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Lock
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# How many events a subscriber may fall behind before it starts losing them. Generous
# relative to a run's thirteen-odd events, so falling behind means a reader that has
# stopped reading rather than one that is merely slow.
SUBSCRIBER_BACKLOG = 256


@dataclass(frozen=True, slots=True)
class Event:
    """One thing that happened, as it travels to a watcher.

    Carries its sequence so a client can deduplicate across a reconnect: a replayed event
    and a live one are the same event, and only the sequence says so.
    """

    run_id: UUID
    sequence: int
    kind: str
    payload: dict[str, Any]


class Subscription:
    """One watcher's view of one run.

    A queue rather than a callback: the reader is an SSE handler on an event loop and the
    writer is a worker thread, and a callback would run the handler's work on the worker's
    thread.
    """

    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        self._events: Queue[Event | None] = Queue(maxsize=SUBSCRIBER_BACKLOG)

    def deliver(self, event: Event) -> bool:
        """Hand an event over. Returns whether it fitted."""
        try:
            self._events.put_nowait(event)
        except Full:
            return False
        return True

    def close(self) -> None:
        """Wake the reader so it can stop, rather than waiting for an event that will not
        come."""
        # A backlog full at close is one already being drained; the reader will notice the
        # run has finished without needing this.
        with suppress(Full):
            self._events.put_nowait(None)

    def next(self, timeout: float) -> Event | None:
        """The next event, or ``None`` if none arrived in time or the stream ended.

        One return value for both, because the caller does the same thing either way:
        check whether the run has finished, then wait again.
        """
        try:
            return self._events.get(timeout=timeout)
        except Empty:
            return None


class EventBus:
    """Fan-out from one run to whoever is watching it."""

    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[Subscription]] = defaultdict(set)
        self._lock = Lock()

    def subscribe(self, run_id: UUID) -> Subscription:
        subscription = Subscription(run_id)
        with self._lock:
            self._subscribers[run_id].add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            watchers = self._subscribers.get(subscription.run_id)
            if watchers is not None:
                watchers.discard(subscription)
                if not watchers:
                    # Otherwise a long-lived process accumulates one empty set per run it
                    # has ever served.
                    del self._subscribers[subscription.run_id]
        subscription.close()

    def publish(self, event: Event) -> int:
        """Deliver to everyone watching that run. Returns how many received it.

        Never blocks and never raises. The worker publishing this is between two nodes of
        somebody's diagnosis, and a watcher's problem must not become theirs.
        """
        with self._lock:
            watchers = list(self._subscribers.get(event.run_id, ()))

        delivered = 0
        for subscription in watchers:
            if subscription.deliver(event):
                delivered += 1
            else:
                logger.warning(
                    "dropped event %s for run %s: subscriber is not reading",
                    event.sequence,
                    event.run_id,
                )
        return delivered

    def close_run(self, run_id: UUID) -> None:
        """Tell every watcher of a finished run that there will be nothing more."""
        with self._lock:
            watchers = list(self._subscribers.pop(run_id, ()))
        for subscription in watchers:
            subscription.close()

    @property
    def watched_runs(self) -> int:
        """How many runs have somebody watching. For tests, and for a health check later."""
        with self._lock:
            return len(self._subscribers)


# One bus for the process, because there is one pool in the same process feeding it.
bus = EventBus()
