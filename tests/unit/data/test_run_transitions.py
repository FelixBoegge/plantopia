"""Status transitions, and what happens when two of them race.

Two things write a run's status: the worker advancing it, and a request cancelling or
answering it. A read-then-write loses one of them silently, under exactly the timing a test
does not reproduce — so every transition names the status it expects to find, and the loser
is told it lost.

The concurrency test uses two real connections rather than two sessions on one, because a
savepoint on a shared connection is not a second writer and would prove nothing.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from data.engine import build_sessions
from data.models import Run
from data.repositories import runs as run_status
from data.repositories.runs import RunRepository
from tests.people import make_owner
from tests.runs import NOW, make_run


@pytest.fixture
def repo(db):
    return RunRepository(db)


def test_a_run_advances_from_the_status_it_is_in(db, repo):
    run = make_run(db, make_owner(db), status=run_status.QUEUED)

    moved = repo.advance(run.id, expected=run_status.QUEUED, to=run_status.RUNNING, now=NOW)

    assert moved is True
    assert repo.get(run.user_id, run.id).status == run_status.RUNNING


def test_a_run_does_not_advance_from_a_status_it_is_not_in(db, repo):
    """The whole mechanism. A worker finishing a node while a cancellation lands must not
    resurrect the run by writing `running` over `cancelled`.
    """
    run = make_run(db, make_owner(db), status=run_status.CANCELLED)

    moved = repo.advance(run.id, expected=run_status.RUNNING, to=run_status.COMPLETED, now=NOW)

    assert moved is False
    assert repo.get(run.user_id, run.id).status == run_status.CANCELLED


def test_a_transition_may_accept_more_than_one_starting_status(db, repo):
    """Cancelling applies to a run that is queued, running or waiting — one call, three
    legitimate starting points."""
    run = make_run(db, make_owner(db), status=run_status.AWAITING_ANSWERS)

    moved = repo.advance(run.id, expected=run_status.UNFINISHED, to=run_status.CANCELLED, now=NOW)

    assert moved is True


def test_advancing_records_when_the_status_changed(db, repo):
    """Both ceilings measure from this. A transition that left it alone would make a run
    that has just started look like one stuck for an hour."""
    run = make_run(db, make_owner(db), status=run_status.QUEUED, now=NOW)
    later = NOW + timedelta(minutes=5)

    repo.advance(run.id, expected=run_status.QUEUED, to=run_status.RUNNING, now=later)

    assert repo.get(run.user_id, run.id).status_changed_at == later


def test_reaching_a_terminal_status_records_when_it_finished(db, repo):
    run = make_run(db, make_owner(db), status=run_status.RUNNING)

    repo.advance(run.id, expected=run_status.RUNNING, to=run_status.COMPLETED, now=NOW)

    assert repo.get(run.user_id, run.id).finished_at == NOW


def test_a_non_terminal_status_does_not_record_a_finish(db, repo):
    run = make_run(db, make_owner(db), status=run_status.QUEUED)

    repo.advance(run.id, expected=run_status.QUEUED, to=run_status.RUNNING, now=NOW)

    assert repo.get(run.user_id, run.id).finished_at is None


def test_a_transition_can_carry_what_the_run_produced(db, repo):
    run = make_run(db, make_owner(db), status=run_status.RUNNING)

    repo.advance(
        run.id,
        expected=run_status.RUNNING,
        to=run_status.FAILED,
        now=NOW,
        error="the run could not be completed",
    )

    assert repo.get(run.user_id, run.id).error == "the run could not be completed"


def test_a_worker_holding_a_stale_run_cannot_overwrite_a_cancellation(pg_engine):
    """The race, interleaved deliberately rather than raced for.

    Two real connections. The worker loads the run while it is ``running`` — as it does
    between two nodes — and a cancellation lands and commits before the worker tries to
    finish. The worker must be told it lost, not silently resurrect the run by writing
    ``completed`` over ``cancelled``.

    Deterministic on purpose. Two threads and a barrier looked like a stronger test and was
    a weaker one: they never overlapped, and a read-then-write implementation passed it.
    """
    sessions = build_sessions(pg_engine)
    setup = sessions()
    owner = make_owner(setup)
    run_id = make_run(setup, owner, status=run_status.RUNNING).id
    setup.commit()
    setup.close()

    worker, canceller = sessions(), sessions()
    try:
        # The worker has the run in hand, believing it is running.
        loaded = worker.scalar(select(Run).where(Run.id == run_id))
        assert loaded.status == run_status.RUNNING

        cancelled = RunRepository(canceller).advance(
            run_id, expected=run_status.UNFINISHED, to=run_status.CANCELLED, now=datetime.now(UTC)
        )
        canceller.commit()

        finished = RunRepository(worker).advance(
            run_id, expected=run_status.RUNNING, to=run_status.COMPLETED, now=datetime.now(UTC)
        )
        worker.commit()

        final = sessions()
        try:
            status = final.scalar(select(Run.status).where(Run.id == run_id))
        finally:
            final.close()
    finally:
        cleanup = sessions()
        cleanup.execute(Run.__table__.delete().where(Run.id == run_id))
        cleanup.commit()
        cleanup.close()
        worker.close()
        canceller.close()

    assert cancelled is True
    assert finished is False, "the worker overwrote a cancellation it never saw"
    assert status == run_status.CANCELLED


def test_claiming_the_right_to_record_usage_succeeds_once(db, repo):
    """A worker finishing and the sweeper giving up must not both record one run, which
    would charge an owner twice for one diagnosis."""
    run = make_run(db, make_owner(db), status=run_status.RUNNING)

    assert repo.mark_usage_recorded(run.id) is True
    assert repo.mark_usage_recorded(run.id) is False


def test_a_cancelled_run_reports_that_a_stop_was_asked_for(db, repo):
    owner = make_owner(db)
    run = make_run(db, owner, status=run_status.RUNNING)

    repo.request_cancel(owner, run.id)

    assert repo.cancel_requested(run.id) is True


def test_a_run_nobody_cancelled_reports_so(db, repo):
    run = make_run(db, make_owner(db), status=run_status.RUNNING)

    assert repo.cancel_requested(run.id) is False


def test_a_finished_run_cannot_be_asked_to_stop(db, repo):
    """Not an error the repository raises — the caller reads the run first, and turns the
    two possible reasons into 404 and 409 respectively."""
    owner = make_owner(db)
    run = make_run(db, owner, status=run_status.COMPLETED)

    assert repo.request_cancel(owner, run.id) is False


def test_the_sweeper_sees_only_runs_older_than_the_moment_it_asks_about(db, repo):
    owner = make_owner(db)
    old = make_run(db, owner, status=run_status.RUNNING, now=NOW - timedelta(hours=2))
    make_run(db, owner, status=run_status.RUNNING, now=NOW)

    stuck = repo.unfinished_since_before(
        NOW - timedelta(hours=1), statuses=frozenset({run_status.RUNNING})
    )

    assert stuck == [old.id]


def test_the_sweeper_sees_only_the_statuses_it_asks_about(db, repo):
    """The two ceilings are separate, so each query is separate — one number for both would
    either reap live conversations or leave dead runs for hours."""
    owner = make_owner(db)
    working = make_run(db, owner, status=run_status.RUNNING, now=NOW - timedelta(hours=2))
    make_run(db, owner, status=run_status.AWAITING_ANSWERS, now=NOW - timedelta(hours=2))

    stuck = repo.unfinished_since_before(
        NOW - timedelta(hours=1), statuses=frozenset({run_status.RUNNING})
    )

    assert stuck == [working.id]
