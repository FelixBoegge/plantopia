"""Failing runs that stopped without saying so.

A process restarted mid-run leaves rows saying ``running`` that nothing is running. Without
this they sit there: a client waits on them forever, and each one counts against its
owner's allowance while producing nothing.

**Two ceilings, because waiting for a person is not the same as being stuck.** A run still
``running`` past the first is a process that died. One ``awaiting_answers`` past the second
is somebody who closed the tab. A single number would either reap live conversations or
leave dead runs for hours.

**Idempotent.** It claims each run with a conditional transition and claims the right to
record usage separately, so a sweep racing a worker that is finishing produces one winner —
and an owner is never charged twice for one diagnosis.

**A swept run still counts against its owner's allowance**, with its cost recorded as
unknown. What it actually spent died with the process that was spending it, and unknown is
the honest value — but recording nothing would make crashing a way to run for free, which
is the one reading of "we could not measure it" nobody should be able to rely on.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import Settings
from data.engine import transaction
from data.repositories import runs as run_status
from data.repositories.runs import RunRepository
from data.repositories.usage import UsageRepository
from runs import steps
from runs.bus import Event, EventBus
from services import limits

logger = logging.getLogger(__name__)

# What a swept run records, distinct from a run that failed while working. Somebody reading
# the table later needs to tell "the model refused" from "the process went away".
ABANDONED = "The run stopped responding and was ended. You can try again."
UNANSWERED = "Nobody answered the questions in time, so the run was ended."


def sweep(
    session: Session, *, settings: Settings, bus: EventBus, now: datetime | None = None
) -> int:
    """End every run that has overrun its ceiling. Returns how many.

    Not owner-scoped: this is a property of the deployment, like the daily spend cap.
    """
    moment = now or datetime.now(UTC)
    runs = RunRepository(session)

    swept = 0
    swept += _reap(
        runs,
        session,
        bus,
        statuses=frozenset({run_status.QUEUED, run_status.RUNNING}),
        before=moment - timedelta(minutes=settings.run_working_ceiling_minutes),
        reason=ABANDONED,
        now=moment,
    )
    swept += _reap(
        runs,
        session,
        bus,
        statuses=frozenset({run_status.AWAITING_ANSWERS}),
        before=moment - timedelta(minutes=settings.run_answering_ceiling_minutes),
        reason=UNANSWERED,
        now=moment,
    )
    return swept


def _reap(runs, session, bus, *, statuses, before, reason, now) -> int:
    """Fail the runs of one kind that are past their own ceiling."""
    swept = 0
    for run_id in runs.unfinished_since_before(before, statuses=statuses):
        with transaction(session):
            claimed = runs.advance(
                run_id, expected=statuses, to=run_status.FAILED, now=now, error=reason
            )
            if not claimed:
                # A worker finished it between the query and here. Its result stands.
                continue
            payload = {"detail": reason}
            sequence = runs.append_event(run_id, kind=steps.FAILED, payload=payload, now=now)
            _record_unmeasured_usage(session, runs, run_id, now=now)

        bus.publish(Event(run_id=run_id, sequence=sequence, kind=steps.FAILED, payload=payload))
        bus.close_run(run_id)
        swept += 1
        logger.warning("run %s exceeded its ceiling and was ended: %s", run_id, reason)
    return swept


def _record_unmeasured_usage(session, runs, run_id, *, now) -> None:
    """Count a swept run against its owner, for whatever of it was measured.

    Claimed conditionally, so a worker that recorded its own usage before dying keeps that
    record and this adds nothing.

    **A swept run is usually not unmeasured.** The commonest thing to sweep is a run
    abandoned at the clarifying-question interrupt, and that pause wrote down what the
    pass before it spent — the vision and gate calls, which are the expensive ones. Those
    were real money and they are charged. This used to record a null cost regardless, so
    a diagnosis somebody started and never answered was free.

    Still ``None`` when there is nothing stored, which is the honest answer for a run
    whose collector went with the process: inventing a number would put a guess where a
    measurement belongs.
    """
    from data.models import Run

    if not runs.mark_usage_recorded(run_id):
        return
    owner = session.scalar(select(Run.user_id).where(Run.id == run_id))
    if owner is None:  # pragma: no cover - the run was just read
        return
    UsageRepository(session).record(
        owner,
        kind=limits.DIAGNOSIS,
        usage=runs.partial_usage_of(run_id),
        succeeded=False,
        now=now,
    )


def run_periodically(settings: Settings, bus: EventBus, stop) -> None:
    """Sweep on a schedule until asked to stop.

    A loop on its own thread rather than a scheduler library: it does one thing, on one
    interval, and a dependency for that would be a dependency to keep current.

    Opens and closes a session per pass. Holding one between sweeps would keep a pooled
    connection idle for a minute at a time, and a connection that has been idle through a
    database restart is one that fails on its next use.
    """
    from agent.wiring import open_session

    while not stop.wait(settings.run_sweeper_interval_seconds):
        session = open_session(settings)
        try:
            swept = sweep(session, settings=settings, bus=bus)
            if swept:
                logger.info("ended %d abandoned run(s)", swept)
        except Exception:  # pragma: no cover - a sweep failing must not stop sweeping
            logger.exception("a sweep failed; the next one will try again")
        finally:
            session.close()
