"""Where a run's work actually happens.

A port with one adapter, and the port is the point. The workload is a handful of
concurrent, IO-bound HTTP calls, so a thread pool inside the API process is the honest
size of it — Celery or arq would be a second service, a second deploy target and a second
failure mode for something that fits here. Everything durable is in Postgres, so a crash
loses the in-flight step and nothing else.

**The queue is bounded, and a full one is a refusal.** Unbounded, a burst becomes a pile of
runs that each take minutes and each hold a checkpoint, and the person who submitted the
last one waits half an hour without being told to come back. Refusing is the only answer
that is true.

**Submitting does not block.** A caller is inside a request; a pool that made them wait for
a slot would reintroduce the blocking request this whole change exists to remove.
"""

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QueueFullError(Exception):
    """More work is waiting than the queue will hold.

    Its own exception, and not a quota: this one clears on its own in a minute, which is a
    materially different thing to tell somebody than "you have used your allowance" or
    "the deployment is out of budget for today".
    """

    depth: int
    limit: int

    def __str__(self) -> str:
        return f"{self.depth} runs already waiting, limit {self.limit}"


class RunExecutor(Protocol):
    """Somewhere to put work that must not happen inside a request."""

    def submit(self, work: Callable[[], None]) -> None:
        """Run this, later, on somebody else's thread.

        Returns as soon as the work is accepted. Raises ``QueueFullError`` when it is not.
        """
        ...

    def shutdown(self) -> None:
        """Stop accepting work and wait for what is in flight."""
        ...


class ThreadPoolRunExecutor:
    """The adapter: a bounded pool inside this process."""

    def __init__(self, *, pool_size: int, queue_limit: int) -> None:
        self._pool = ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix="run")
        self._queue_limit = queue_limit
        self._lock = Lock()
        self._in_flight = 0

    def submit(self, work: Callable[[], None]) -> None:
        with self._lock:
            if self._in_flight >= self._queue_limit:
                raise QueueFullError(depth=self._in_flight, limit=self._queue_limit)
            self._in_flight += 1

        try:
            future = self._pool.submit(self._guarded, work)
        except RuntimeError:
            # The pool is shutting down. Release the slot rather than leaking it, so a
            # process being restarted does not report a full queue on the way down.
            with self._lock:
                self._in_flight -= 1
            raise

        future.add_done_callback(self._released)

    @property
    def in_flight(self) -> int:
        """How much work is queued or running. For the queue check and for tests."""
        with self._lock:
            return self._in_flight

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)

    def _guarded(self, work: Callable[[], None]) -> None:
        """Run one piece of work, and never let it take the worker with it.

        A pool whose thread dies on an exception is a pool that silently loses capacity —
        and the run that caused it is exactly the run nobody was watching.
        """
        try:
            work()
        except Exception:
            logger.exception("a background run raised; the worker continues")

    def _released(self, future: Future) -> None:
        with self._lock:
            self._in_flight -= 1


def build_executor(settings) -> ThreadPoolRunExecutor:
    """The executor this configuration implies."""
    return ThreadPoolRunExecutor(
        pool_size=settings.run_pool_size, queue_limit=settings.run_queue_limit
    )
