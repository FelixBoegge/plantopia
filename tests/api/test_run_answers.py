"""Answering the questions a paused run asked.

The refusals matter more than the happy path here. A second submission that started a
second pass would run the expensive half of a diagnosis twice against one checkpoint, and
the two would race to write the same run's status.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends
from sqlalchemy.orm import Session

from api import dependencies, errors
from core.config import Settings
from core.ids import new_id
from data.repositories import runs as run_status
from data.repositories.plants import PlantRepository
from data.repositories.runs import RunRepository
from data.repositories.usage import UsageRepository
from runs import steps
from runs.bus import bus
from services.run_service import RunService
from tests.runs import make_run

ANSWERS = {"answers": {"watering": "every other day"}}


class RecordingExecutor:
    """Accepts work and never runs it, so a resume is observable as a submission."""

    def __init__(self) -> None:
        self.submitted: list = []

    def submit(self, work) -> None:
        self.submitted.append(work)

    def shutdown(self) -> None:  # pragma: no cover
        pass


@pytest.fixture
def executor(client, db):
    recorder = RecordingExecutor()

    def _service(
        session: Annotated[Session, Depends(dependencies.session_dep)],
        owner: Annotated[UUID, Depends(dependencies.current_owner)],
        settings: Annotated[Settings, Depends(dependencies.settings_dep)],
    ):
        return RunService(
            user_id=owner,
            tier="free",
            runs=RunRepository(session),
            plants=PlantRepository(session),
            usage=UsageRepository(session),
            executor=recorder,
            bus=bus,
            settings=settings,
            now=lambda: datetime.now(UTC),
        )

    client.app.dependency_overrides[dependencies.run_service] = _service
    return recorder


@pytest.fixture
def waiting(db, owner):
    """A run paused for answers, which is the only state answering makes sense in."""
    run = make_run(db, owner, status=run_status.AWAITING_ANSWERS)
    run_id = run.id
    db.commit()
    return run_id


def _answer(client, run_id, body=None):
    return client.post(f"/api/v1/runs/{run_id}/answers", json=body or ANSWERS)


def test_answering_a_waiting_run_queues_it_again(client, db, waiting, executor):
    response = _answer(client, waiting)

    assert response.status_code == 200
    assert response.json()["status"] == run_status.QUEUED


def test_answering_hands_the_resume_to_the_executor(client, waiting, executor):
    _answer(client, waiting)

    assert len(executor.submitted) == 1


def test_answering_carries_the_answers_to_the_worker(client, waiting, executor):
    """The whole point of the request. A resume with no answers would pause again."""
    import inspect

    _answer(client, waiting)
    closure = inspect.getclosurevars(executor.submitted[0]).nonlocals

    assert closure["resume"] == ANSWERS["answers"]


def test_answering_twice_is_a_conflict(client, db, waiting, executor):
    """Two passes over one checkpoint would run the expensive half twice and race to write
    the same status."""
    _answer(client, waiting)

    second = _answer(client, waiting)

    assert second.status_code == 409
    assert second.json()["type"] == errors.TYPE_CONFLICT


def test_a_second_answer_starts_nothing(client, db, waiting, executor):
    _answer(client, waiting)

    _answer(client, waiting)

    assert len(executor.submitted) == 1


def test_a_second_answer_leaves_the_first_alone(client, db, waiting, executor):
    """Field by field. A refusal that nudged a timestamp would be a refusal that changed
    something."""
    _answer(client, waiting)
    after_first = client.get(f"/api/v1/runs/{waiting}").json()

    _answer(client, waiting)

    assert client.get(f"/api/v1/runs/{waiting}").json() == after_first


@pytest.mark.parametrize(
    "status",
    [
        run_status.QUEUED,
        run_status.RUNNING,
        run_status.COMPLETED,
        run_status.FAILED,
        run_status.CANCELLED,
    ],
)
def test_answering_a_run_that_is_not_waiting_is_a_conflict(client, db, owner, executor, status):
    run = make_run(db, owner, status=status)
    run_id = run.id
    db.commit()

    response = _answer(client, run_id)

    assert response.status_code == 409
    assert executor.submitted == []


@pytest.mark.parametrize(
    "status",
    [run_status.QUEUED, run_status.RUNNING, run_status.COMPLETED, run_status.CANCELLED],
)
def test_a_refused_answer_does_not_change_the_status(client, db, owner, executor, status):
    run = make_run(db, owner, status=status)
    run_id = run.id
    db.commit()

    _answer(client, run_id)

    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == status


def test_answering_another_owners_run_is_absent(client, db, other_owner, executor):
    theirs = make_run(db, other_owner, status=run_status.AWAITING_ANSWERS)
    run_id = theirs.id
    db.commit()

    response = _answer(client, run_id)

    assert response.status_code == 404
    assert response.json()["type"] == errors.TYPE_NOT_FOUND


def test_answering_another_owners_run_leaves_it_waiting(client, db, other_owner, executor):
    """404 rather than 409, and nothing moved: a stranger must not be able to tell a run
    that exists from one that does not, nor disturb it."""
    theirs = make_run(db, other_owner, status=run_status.AWAITING_ANSWERS)
    run_id = theirs.id
    db.commit()

    _answer(client, run_id)

    assert RunRepository(db).get(other_owner, run_id).status == run_status.AWAITING_ANSWERS
    assert executor.submitted == []


def test_answering_an_unknown_run_answers_the_same_way(client, db, other_owner, executor):
    theirs = make_run(db, other_owner, status=run_status.AWAITING_ANSWERS)
    run_id = theirs.id
    db.commit()

    forbidden = _answer(client, run_id)
    unknown = _answer(client, new_id())

    assert forbidden.status_code == unknown.status_code
    assert forbidden.json() == unknown.json()


def test_answers_are_required(client, waiting, executor):
    response = client.post(f"/api/v1/runs/{waiting}/answers", json={})

    assert response.status_code == 422
    assert executor.submitted == []


def test_cancelling_an_unfinished_run_is_accepted(client, db, waiting, executor):
    response = client.delete(f"/api/v1/runs/{waiting}")

    assert response.status_code == 204


def test_cancelling_a_running_run_asks_the_worker_to_stop(client, db, owner, executor):
    """A flag read between nodes, not a status: the run is still legitimately running until
    the worker notices, and a status meaning "will stop shortly" is one every client would
    have to special-case."""
    run = make_run(db, owner, status=run_status.RUNNING)
    run_id = run.id
    db.commit()

    client.delete(f"/api/v1/runs/{run_id}")

    assert RunRepository(db).cancel_requested(run_id) is True
    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == run_status.RUNNING


def test_cancelling_a_paused_run_ends_it_immediately(client, db, waiting, executor):
    """Nothing is executing, so there is no worker to notice a flag. A run told to stop
    would otherwise sit paused until the sweeper gave up on it an hour later."""
    client.delete(f"/api/v1/runs/{waiting}")

    assert client.get(f"/api/v1/runs/{waiting}").json()["status"] == run_status.CANCELLED


def test_a_cancelled_paused_run_cannot_then_be_answered(client, db, waiting, executor):
    """Answering it would restart work somebody has already said they do not want."""
    client.delete(f"/api/v1/runs/{waiting}")

    response = _answer(client, waiting)

    assert response.status_code == 409
    assert executor.submitted == []


def test_cancelling_a_queued_run_ends_it_immediately(client, db, owner, executor):
    run = make_run(db, owner, status=run_status.QUEUED)
    run_id = run.id
    db.commit()

    client.delete(f"/api/v1/runs/{run_id}")

    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == run_status.CANCELLED


def test_a_cancelled_paused_run_says_so_on_its_stream(client, db, owner, waiting, executor):
    """A watcher would otherwise hold a connection open on something that has ended."""
    client.delete(f"/api/v1/runs/{waiting}")

    events = RunRepository(db).events(owner, waiting)
    assert [event.kind for event in events] == [steps.CANCELLED]


@pytest.mark.parametrize(
    "status", [run_status.QUEUED, run_status.RUNNING, run_status.AWAITING_ANSWERS]
)
def test_every_unfinished_status_can_be_cancelled(client, db, owner, executor, status):
    run = make_run(db, owner, status=status)
    run_id = run.id
    db.commit()

    assert client.delete(f"/api/v1/runs/{run_id}").status_code == 204


@pytest.mark.parametrize("status", [run_status.COMPLETED, run_status.FAILED, run_status.CANCELLED])
def test_cancelling_a_finished_run_is_a_conflict(client, db, owner, executor, status):
    run = make_run(db, owner, status=status)
    run_id = run.id
    db.commit()

    response = client.delete(f"/api/v1/runs/{run_id}")

    assert response.status_code == 409
    assert response.json()["type"] == errors.TYPE_CONFLICT


@pytest.mark.parametrize("status", [run_status.COMPLETED, run_status.FAILED, run_status.CANCELLED])
def test_a_refused_cancellation_changes_nothing(client, db, owner, executor, status):
    run = make_run(db, owner, status=status)
    run_id = run.id
    db.commit()
    before = client.get(f"/api/v1/runs/{run_id}").json()

    client.delete(f"/api/v1/runs/{run_id}")

    assert client.get(f"/api/v1/runs/{run_id}").json() == before


def test_cancelling_another_owners_run_is_absent(client, db, other_owner, executor):
    theirs = make_run(db, other_owner, status=run_status.RUNNING)
    run_id = theirs.id
    db.commit()

    response = client.delete(f"/api/v1/runs/{run_id}")

    assert response.status_code == 404


def test_cancelling_another_owners_run_does_not_ask_it_to_stop(client, db, other_owner, executor):
    theirs = make_run(db, other_owner, status=run_status.RUNNING)
    run_id = theirs.id
    db.commit()

    client.delete(f"/api/v1/runs/{run_id}")

    assert RunRepository(db).cancel_requested(run_id) is False
