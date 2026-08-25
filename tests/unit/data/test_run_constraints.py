"""What the database refuses about a run, as opposed to what Python refuses.

Status is the contract a client reads. A constraint in application code is a constraint
until somebody writes a row another way — a migration, a fixture, a repair script — and the
value that arrives at a client is then one nothing knows how to render.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from core.ids import new_id
from data.models import Run
from tests.people import make_owner
from tests.runs import NOW, make_run

VALID_STATUSES = (
    "queued",
    "running",
    "awaiting_answers",
    "completed",
    "failed",
    "cancelled",
)


@pytest.mark.parametrize("status", VALID_STATUSES)
def test_every_status_the_contract_names_is_accepted(db, status):
    """The other half of the constraint test: a rule that refuses everything passes a test
    that only checks it refuses nonsense."""
    make_run(db, make_owner(db), status=status)

    assert db.scalar(db.query(Run).filter(Run.status == status).exists().select())


def test_an_invented_status_is_refused_by_the_database(db):
    owner = make_owner(db)
    db.flush()

    db.add(
        Run(
            id=new_id(),
            user_id=owner,
            plant_id=None,
            kind="diagnosis",
            thread_id="t",
            status="nearly-done",
            created_at=NOW,
            status_changed_at=NOW,
        )
    )

    with pytest.raises(IntegrityError):
        db.flush()


def test_an_invented_kind_is_refused_by_the_database(db):
    owner = make_owner(db)
    db.flush()

    db.add(
        Run(
            id=new_id(),
            user_id=owner,
            plant_id=None,
            kind="speculation",
            thread_id="t",
            status="queued",
            created_at=NOW,
            status_changed_at=NOW,
        )
    )

    with pytest.raises(IntegrityError):
        db.flush()


def test_two_events_cannot_share_a_sequence_within_one_run(db):
    """What replay depends on. Two events at sequence 4 make "everything after 3"
    ambiguous, and a client that reconnects renders one of them twice or neither."""
    from data.models import RunEvent

    run = make_run(db, make_owner(db))
    db.add(RunEvent(run_id=run.id, sequence=1, kind="step", payload_json="{}", occurred_at=NOW))
    db.flush()

    db.add(RunEvent(run_id=run.id, sequence=1, kind="step", payload_json="{}", occurred_at=NOW))

    with pytest.raises(IntegrityError):
        db.flush()


def test_two_runs_may_each_have_their_own_sequence_one(db):
    """The sequence is per run, not global. Sharing a counter would make the replay query
    a scan across everybody's events."""
    from data.models import RunEvent

    owner = make_owner(db)
    first, second = make_run(db, owner), make_run(db, owner)

    db.add(RunEvent(run_id=first.id, sequence=1, kind="step", payload_json="{}", occurred_at=NOW))
    db.add(RunEvent(run_id=second.id, sequence=1, kind="step", payload_json="{}", occurred_at=NOW))

    db.flush()  # must not raise
