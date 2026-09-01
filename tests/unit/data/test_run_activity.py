"""Reading back what the run that produced a diagnosis did.

Nothing new is stored for this. Every step is already written to ``run_events`` before it is
published, and a run already records the diagnosis it produced, so the whole history is in
the database — the only thing that was missing was a way in from the result.
"""

from uuid import uuid4

from data.repositories.runs import RunRepository
from runs import steps
from tests.accounts import NOW, populate
from tests.runs import make_run


def _run_for(db, account, **overrides):
    run = make_run(
        db,
        account.user_id,
        plant_id=account.plant_id,
        diagnosis_id=account.diagnosis_id,
        **overrides,
    )
    db.flush()
    return run


def test_the_steps_of_the_run_that_produced_a_diagnosis_are_readable(db):
    account = populate(db)
    run = _run_for(db, account)
    repo = RunRepository(db)
    repo.append_event(run.id, kind=steps.STEP, payload={"step": "identifying"}, now=NOW)

    found = repo.steps_for_diagnosis(account.user_id, account.diagnosis_id)

    assert [event.payload["step"] for event in found] == ["identifying"]


def test_only_steps_come_back(db):
    """A run's other events belong to the run. The screen reading this is showing what was
    consulted, not how the run ended."""
    account = populate(db)
    run = _run_for(db, account)
    repo = RunRepository(db)
    repo.append_event(run.id, kind=steps.STEP, payload={"step": "identifying"}, now=NOW)
    repo.append_event(run.id, kind=steps.COMPLETED, payload={"rejected": False}, now=NOW)

    found = repo.steps_for_diagnosis(account.user_id, account.diagnosis_id)

    assert [event.kind for event in found] == [steps.STEP]


def test_they_come_back_in_the_order_they_happened(db):
    account = populate(db)
    run = _run_for(db, account)
    repo = RunRepository(db)
    for name in ("checking", "identifying", "diagnosing"):
        repo.append_event(run.id, kind=steps.STEP, payload={"step": name}, now=NOW)

    found = repo.steps_for_diagnosis(account.user_id, account.diagnosis_id)

    assert [event.payload["step"] for event in found] == ["checking", "identifying", "diagnosing"]


def test_another_owner_reads_nothing(db):
    """Scoped through the run, like every other read here. A stranger holding a diagnosis
    identifier learns nothing from it — and the identifier is the only thing they would
    otherwise need."""
    account = populate(db)
    stranger = populate(db, password="a-different-long-password")
    run = _run_for(db, account)
    repo = RunRepository(db)
    repo.append_event(run.id, kind=steps.STEP, payload={"step": "identifying"}, now=NOW)

    assert repo.steps_for_diagnosis(stranger.user_id, account.diagnosis_id) == []


def test_a_diagnosis_with_no_run_reads_as_empty(db):
    account = populate(db)

    assert RunRepository(db).steps_for_diagnosis(account.user_id, uuid4()) == []
