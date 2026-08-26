"""A run driven through the service, not around it.

This file exists because of a bug that neither side's unit tests could see. The service
moved a resumed run to ``queued`` before submitting it; the worker expected to find it
``awaiting_answers``. Each was self-consistent and well tested, and together they meant no
resumed run ever started — it sat queued until the sweeper failed it, an hour later, with a
message about a process that had never gone away.

Both halves are exercised here, with an executor that runs work where it stands. What is
faked is the graph and the clock; what is real is every hand-off between them.
"""

from datetime import UTC, datetime

import pytest
from langgraph.checkpoint.memory import MemorySaver

from agent.diagnosis_graph import build_diagnosis_graph
from core.config import Settings
from data.repositories import runs as run_status
from data.repositories.plants import PlantRepository
from data.repositories.runs import RunRepository
from data.repositories.usage import UsageRepository
from runs.bus import EventBus
from services.run_service import RunConflictError, RunService, StartRequest
from tests.secrets import TEST_JWT_SECRET

ANSWERS = {"watering": "every other day", "drainage": "No drainage holes"}


class Inline:
    """An executor that runs work immediately, on this thread.

    The pool has its own tests. Here it would only add timing to a question about who hands
    what to whom.
    """

    def submit(self, work) -> None:
        work()

    def shutdown(self) -> None:  # pragma: no cover
        pass


@pytest.fixture
def settings():
    return Settings(_env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET)


@pytest.fixture
def service(db, owner, settings, make_deps, make_pipeline_models):
    """The real service, with a scripted graph behind it and nothing else replaced."""
    gate, vision, chat = make_pipeline_models()
    graph = build_diagnosis_graph(
        make_deps(gate_model=gate, vision_model=vision, chat_model=chat), MemorySaver()
    )

    return RunService(
        user_id=owner,
        tier="free",
        runs=RunRepository(db),
        plants=PlantRepository(db),
        usage=UsageRepository(db),
        executor=Inline(),
        bus=EventBus(),
        settings=settings,
        now=lambda: datetime.now(UTC),
        build_graph=lambda **_: graph,
        # The worker's own session by default opens a second connection, which cannot see
        # this test's uncommitted data — it would find no run and quietly do nothing.
        session_factory=lambda: db,
    )


@pytest.fixture
def started(service, sample_images, db):
    db.commit()
    return service.start(
        StartRequest(images=sample_images, plant_name="Kitchen basil", location_kind="indoor")
    )


def test_starting_a_run_reaches_the_interrupt(service, started):
    assert service.get(started.id).status == run_status.AWAITING_ANSWERS


def test_answering_a_run_actually_resumes_it(service, started):
    """The one this file was written for. Before the fix this left the run queued, and
    nothing was coming to pick it up."""
    service.answer(started.id, ANSWERS)

    assert service.get(started.id).status == run_status.COMPLETED


def test_a_resumed_run_produces_a_diagnosis(service, started):
    service.answer(started.id, ANSWERS)

    assert service.get(started.id).diagnosis_id is not None


def test_a_resumed_run_continues_rather_than_starting_again(service, started):
    """Its events run on from where they paused. A run that restarted would repeat the
    first half's steps — and pay for them again."""
    before = [event.sequence for event in service.events(started.id)]

    service.answer(started.id, ANSWERS)
    after = [event.sequence for event in service.events(started.id)]

    assert after[: len(before)] == before
    assert len(after) > len(before)


def test_a_completed_run_records_its_usage_once(service, started, db, owner):
    from sqlalchemy import func, select

    from data.models import UsageEvent

    service.answer(started.id, ANSWERS)

    assert (
        db.scalar(select(func.count()).select_from(UsageEvent).where(UsageEvent.user_id == owner))
        == 1
    )


def test_answering_twice_is_refused_after_a_real_resume(service, started):
    service.answer(started.id, ANSWERS)

    with pytest.raises(RunConflictError):
        service.answer(started.id, ANSWERS)


def test_a_cancelled_run_cannot_be_answered(service, started):
    service.cancel(started.id)

    with pytest.raises(RunConflictError):
        service.answer(started.id, ANSWERS)


def test_a_typed_species_reaches_the_graphs_state(service, sample_images, db, monkeypatch):
    """The seam between an HTTP form and a graph node.

    The router strips a blank one and `identify_plant` decides what leads; this is only the
    carriage between them, which is exactly the kind of thing that is silently dropped in a
    rename and noticed three screens later.
    """
    seen = []
    monkeypatch.setattr(
        "services.run_service.execute",
        lambda **kwargs: seen.append(kwargs.get("initial_state")),
    )

    db.commit()
    service.start(
        StartRequest(
            images=sample_images,
            plant_name="Kitchen basil",
            location_kind="indoor",
            stated_species="Ocimum basilicum",
        )
    )

    assert seen[0].stated_species == "Ocimum basilicum"
