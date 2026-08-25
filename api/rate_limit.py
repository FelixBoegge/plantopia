"""How often one source may call the endpoints worth hammering.

Registration, sign-in and password reset are singled out because they are unauthenticated,
cost something real to serve — an argon2 hash, an email — and each is worth attacking:
sign-in to guess passwords, registration to make accounts, reset to send mail to somebody
else's address.

**Counted per source, never per address.** Keying on the email would make the limit itself
an oracle: an address that runs out of attempts faster than another is an address that
exists. The source is what is limited, and the answer is the same whichever address was
tried.

**In-process, and that is a real limitation.** The counters live in this process's memory,
so two workers permit twice the limit and a restart clears them. That is honest for a single
container and is recorded in `docs/known-limitations.md`; a shared store is the fix when
there is more than one process to share between.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from fastapi import Request

from core.config import Settings


@dataclass(frozen=True, slots=True)
class RateLimitedError(Exception):
    """Too many attempts from one source."""

    retry_after_seconds: int

    def __str__(self) -> str:
        return f"too many attempts; retry in {self.retry_after_seconds} seconds"


class SlidingWindow:
    """Counts attempts per key over a moving window.

    A sliding window rather than a fixed one because a fixed window lets twice the limit
    through across a boundary — the thing somebody hammering an endpoint is looking for.
    """

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int, now: float) -> None:
        """Record an attempt, or raise if the key has had too many.

        Raises before recording, so a refused attempt does not extend the window it was
        refused by — otherwise a client that keeps trying can never get back in.
        """
        with self._lock:
            attempts = self._attempts[key]
            cutoff = now - window_seconds
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()

            if len(attempts) >= limit:
                raise RateLimitedError(
                    retry_after_seconds=max(1, int(attempts[0] + window_seconds - now) + 1)
                )

            attempts.append(now)

    def forget(self) -> None:
        """Drop every counter. For tests, which must not inherit each other's attempts."""
        with self._lock:
            self._attempts.clear()


# One window for the whole process, shared by every limited endpoint. Shared deliberately:
# somebody alternating between register and login is one source hammering, not two.
window = SlidingWindow()


def source_of(request: Request) -> str:
    """Who is asking, as far as the limiter is concerned.

    The socket's address. Behind a proxy this is the proxy unless it is configured to pass
    the original on, which makes the limit global rather than per-source — a failure in the
    direction of refusing too much rather than too little, and one the deployment change
    fixes by configuring forwarded headers.
    """
    return request.client.host if request.client else "unknown"


def limit(request: Request, settings: Settings) -> None:
    """Refuse the request if its source has had too many recently."""
    window.check(
        source_of(request),
        limit=settings.auth_rate_limit,
        window_seconds=settings.auth_rate_window_seconds,
        now=time.monotonic(),
    )
