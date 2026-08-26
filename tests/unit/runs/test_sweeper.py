"""Runs that stopped without saying so.

The two ceilings are the point. Applying one number to both statuses would either reap a
conversation somebody is still reading, or leave a dead run occupying an allowance for
hours — and those are opposite mistakes, so they get opposite tests.
"""

from datetime import UTC, datetime, timedelta

import pytest

from core.config import Settings
from data.repositories import runs as run_status
from data.repositories.runs import RunRepository
from runs import steps
from runs.bus import EventBus
from runs.sweeper import ABANDONED, UNANSWERED, sweep
from tests.people import make_owner
from tests.runs import make_run
from tests.secrets import TEST_JWT_SECRET

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        openrouter_api_key="sk-test",
        jwt_secret=TEST_JWT_SECRET,
        run_working_ceiling_minutes=10,
        run_answering_ceiling_minutes=60,
    )


@pytest.fixture
def bus():
    return EventBus()


def _aged(db, owner, *, status, minutes):
    """A run whose status last changed that long ago."""
    return make_run(db, owner, status=status, now=NOW - timedelta(minutes=minutes))


def test_a_run_stuck_working_is_failed(db, owner, settings, bus):
    """A process restarted mid-run leaves rows saying `running` that nothing is running."""
    run = _aged(db, owner, status=run_status.RUNNING, minutes=30)

    assert sweep(db, settings=settings, bus=bus, now=NOW) == 1
    assert RunRepository(db).get(owner, run.id).status == run_status.FAILED


def test_a_run_still_within_the_working_ceiling_is_left_alone(db, owner, settings, bus):
    run = _aged(db, owner, status=run_status.RUNNING, minutes=5)

    assert sweep(db, settings=settings, bus=bus, now=NOW) == 0
    assert RunRepository(db).get(owner, run.id).status == run_status.RUNNING


def test_a_run_queued_too_long_is_failed(db, owner, settings, bus):
    """A queue refusal leaves a run queued and nothing to pick it up. It is as stuck as one
    whose worker died, and stuck the same way."""
    run = _aged(db, owner, status=run_status.QUEUED, minutes=30)

    sweep(db, settings=settings, bus=bus, now=NOW)

    assert RunRepository(db).get(owner, run.id).status == run_status.FAILED


def test_a_run_waiting_for_answers_gets_the_longer_ceiling(db, owner, settings, bus):
    """Thirty minutes is a person reading their email, not a dead process. Reaping it would
    throw away a run they are about to finish."""
    run = _aged(db, owner, status=run_status.AWAITING_ANSWERS, minutes=30)

    assert sweep(db, settings=settings, bus=bus, now=NOW) == 0
    assert RunRepository(db).get(owner, run.id).status == run_status.AWAITING_ANSWERS


def test_a_run_waiting_far_too_long_is_failed(db, owner, settings, bus):
    run = _aged(db, owner, status=run_status.AWAITING_ANSWERS, minutes=90)

    assert sweep(db, settings=settings, bus=bus, now=NOW) == 1
    assert RunRepository(db).get(owner, run.id).status == run_status.FAILED


def test_the_answering_ceiling_is_measured_from_when_the_questions_were_asked(
    db, owner, settings, bus
):
    """Not from when the run started. A run that worked for an hour and then asked has been
    waiting for no time at all."""
    run = make_run(db, owner, status=run_status.AWAITING_ANSWERS, now=NOW - timedelta(hours=3))
    RunRepository(db).advance(
        run.id,
        expected=run_status.AWAITING_ANSWERS,
        to=run_status.AWAITING_ANSWERS,
        now=NOW - timedelta(minutes=5),
    )
    db.flush()

    assert sweep(db, settings=settings, bus=bus, now=NOW) == 0


def test_a_swept_run_says_why_and_not_how(db, owner, settings, bus):
    """Distinct from a run that failed while working. Somebody reading the table later has
    to tell "the model refused" from "the process went away"."""
    run = _aged(db, owner, status=run_status.RUNNING, minutes=30)

    sweep(db, settings=settings, bus=bus, now=NOW)

    assert RunRepository(db).get(owner, run.id).error == ABANDONED


def test_an_unanswered_run_says_something_different_again(db, owner, settings, bus):
    """The person can act on this one: they abandoned it. The other they cannot."""
    run = _aged(db, owner, status=run_status.AWAITING_ANSWERS, minutes=90)

    sweep(db, settings=settings, bus=bus, now=NOW)

    assert RunRepository(db).get(owner, run.id).error == UNANSWERED
    assert UNANSWERED != ABANDONED


def test_a_swept_run_announces_itself_on_the_stream(db, owner, settings, bus):
    """A watcher would otherwise hold a connection open on a run that has already given up."""
    run = _aged(db, owner, status=run_status.RUNNING, minutes=30)
    watcher = bus.subscribe(run.id)

    sweep(db, settings=settings, bus=bus, now=NOW)

    event = watcher.next(timeout=1.0)
    assert event is not None
    assert event.kind == steps.FAILED


def test_a_swept_run_closes_its_stream(db, owner, settings, bus):
    run = _aged(db, owner, status=run_status.RUNNING, minutes=30)
    watcher = bus.subscribe(run.id)

    sweep(db, settings=settings, bus=bus, now=NOW)
    while watcher.next(timeout=0.1) is not None:
        pass

    assert watcher.closed is True


def test_sweeping_twice_fails_a_run_once(db, owner, settings, bus):
    """The sweep runs on a schedule. A second pass must find nothing to do."""
    _aged(db, owner, status=run_status.RUNNING, minutes=30)

    first = sweep(db, settings=settings, bus=bus, now=NOW)
    second = sweep(db, settings=settings, bus=bus, now=NOW)

    assert (first, second) == (1, 0)


def test_a_swept_run_records_no_second_event(db, owner, settings, bus):
    run = _aged(db, owner, status=run_status.RUNNING, minutes=30)

    sweep(db, settings=settings, bus=bus, now=NOW)
    sweep(db, settings=settings, bus=bus, now=NOW)

    events = RunRepository(db).events(owner, run.id)
    assert [event.kind for event in events] == [steps.FAILED]


def test_a_run_a_worker_finished_first_is_left_alone(db, owner, settings, bus):
    """The race the conditional transition exists for: the worker won between the query and
    the write, and its result stands."""
    run = _aged(db, owner, status=run_status.RUNNING, minutes=30)
    RunRepository(db).advance(run.id, expected=run_status.RUNNING, to=run_status.COMPLETED, now=NOW)
    db.flush()

    assert sweep(db, settings=settings, bus=bus, now=NOW) == 0
    assert RunRepository(db).get(owner, run.id).status == run_status.COMPLETED


def test_a_finished_run_is_never_swept(db, owner, settings, bus):
    for status in (run_status.COMPLETED, run_status.FAILED, run_status.CANCELLED):
        _aged(db, owner, status=status, minutes=600)

    assert sweep(db, settings=settings, bus=bus, now=NOW) == 0


def test_sweeping_crosses_owners(db, settings, bus):
    """A property of the deployment, like the daily cap — not of a person."""
    first, second = make_owner(db), make_owner(db)
    _aged(db, first, status=run_status.RUNNING, minutes=30)
    _aged(db, second, status=run_status.RUNNING, minutes=30)

    assert sweep(db, settings=settings, bus=bus, now=NOW) == 2


def test_the_two_ceilings_apply_independently(db, owner, settings, bus):
    """Twenty minutes: past the working ceiling, well inside the answering one."""
    working = _aged(db, owner, status=run_status.RUNNING, minutes=20)
    waiting = _aged(db, owner, status=run_status.AWAITING_ANSWERS, minutes=20)

    sweep(db, settings=settings, bus=bus, now=NOW)

    repo = RunRepository(db)
    assert repo.get(owner, working.id).status == run_status.FAILED
    assert repo.get(owner, waiting.id).status == run_status.AWAITING_ANSWERS


def test_a_swept_run_counts_against_its_owners_allowance(db, owner, settings, bus):
    """Otherwise crashing is a way to run for free, and "we could not measure it" becomes
    something somebody can arrange on purpose."""
    from sqlalchemy import select

    from data.models import UsageEvent

    _aged(db, owner, status=run_status.RUNNING, minutes=30)

    sweep(db, settings=settings, bus=bus, now=NOW)

    recorded = db.scalars(select(UsageEvent).where(UsageEvent.user_id == owner)).all()
    assert len(recorded) == 1
    assert recorded[0].succeeded is False


def test_a_swept_runs_cost_is_unknown_rather_than_zero(db, owner, settings, bus):
    """The collector went with the process. Zero would read as a free run; unknown reads as
    what it is."""
    from sqlalchemy import select

    from data.models import UsageEvent

    _aged(db, owner, status=run_status.RUNNING, minutes=30)

    sweep(db, settings=settings, bus=bus, now=NOW)

    assert db.scalar(select(UsageEvent.cost_usd).where(UsageEvent.user_id == owner)) is None


def test_a_run_that_already_recorded_its_usage_is_not_recorded_again(db, owner, settings, bus):
    """A worker that finished recording and then died mid-transition. Its measurement is
    better than the sweeper's guess, and charging twice for one diagnosis is worse than
    either."""
    from sqlalchemy import func, select

    from core.cost import UsageSnapshot
    from data.models import UsageEvent
    from data.repositories.usage import UsageRepository
    from services import limits

    run = _aged(db, owner, status=run_status.RUNNING, minutes=30)
    UsageRepository(db).record(
        owner,
        kind=limits.DIAGNOSIS,
        usage=UsageSnapshot(prompt_tokens=900, completion_tokens=100, cost_usd=0.04),
        succeeded=False,
        now=NOW,
    )
    RunRepository(db).mark_usage_recorded(run.id)
    db.flush()

    sweep(db, settings=settings, bus=bus, now=NOW)

    assert db.scalar(select(func.count()).select_from(UsageEvent)) == 1
    assert db.scalar(select(UsageEvent.cost_usd)) == 0.04


def test_sweeping_twice_records_usage_once(db, owner, settings, bus):
    from sqlalchemy import func, select

    from data.models import UsageEvent

    _aged(db, owner, status=run_status.RUNNING, minutes=30)

    sweep(db, settings=settings, bus=bus, now=NOW)
    sweep(db, settings=settings, bus=bus, now=NOW)

    assert db.scalar(select(func.count()).select_from(UsageEvent)) == 1
