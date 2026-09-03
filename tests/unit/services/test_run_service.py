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

# `captured_at` and `location` are among them because the run asks for both on every
# diagnosis now, and the first is required — a resume without it is refused before the run
# is claimed, which is the point of `_require_answers`.
ANSWERS = {
    "watering": "every other day",
    "drainage": "No drainage holes",
    "location": "Berlin",
    "captured_at": "2026-08-10",
}


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


class TestWhatARunInheritsFromItsPlant:
    """Re-diagnosing a plant should not lose what that plant already knows.

    A re-check skips the questions pause — roadmap-step completion answers what it would
    otherwise ask — so nothing on the way in supplies a location. The upload form has no
    location field either. Without this, an outdoor plant with a town on its record produced
    a run that believed it had no location, and the weather lookup, which needs one, quietly
    returned nothing: a first diagnosis with a weather graph and every re-check after it
    without one.
    """

    def _plant(self, db, owner, **overrides):
        fields = {
            "name": "Garden strawberry",
            "species": "Fragaria x ananassa",
            "species_confidence": 0.9,
            "location_kind": "outdoor",
            "location_text": "Frankfurt am Main",
            "photo_ref": None,
            "now": datetime.now(UTC),
        } | overrides
        plant_id = PlantRepository(db).create(owner, **fields)
        db.commit()
        return plant_id

    def test_a_run_on_a_known_plant_inherits_its_location(self, service, db, owner, sample_images):
        plant_id = self._plant(db, owner)

        state = service.state_for(
            StartRequest(images=sample_images, location_kind="outdoor", plant_id=plant_id)
        )

        assert state.location_text == "Frankfurt am Main"

    def test_what_the_request_carries_wins(self, service, db, owner, sample_images):
        """A photograph that says where it was taken is about this photograph; the plant's
        record is about where it usually lives. The specific one wins."""
        plant_id = self._plant(db, owner)

        state = service.state_for(
            StartRequest(
                images=sample_images,
                location_kind="outdoor",
                plant_id=plant_id,
                location_text="Offenbach am Main",
            )
        )

        assert state.location_text == "Offenbach am Main"

    def test_a_plant_with_no_location_inherits_nothing(self, service, db, owner, sample_images):
        plant_id = self._plant(db, owner, location_kind="indoor", location_text=None)

        state = service.state_for(
            StartRequest(images=sample_images, location_kind="indoor", plant_id=plant_id)
        )

        assert state.location_text is None

    def test_a_run_on_a_known_plant_inherits_its_species(self, service, db, owner, sample_images):
        """Re-identifying a plant already on record costs a vision call and a Pl@ntNet call
        to arrive at an answer the database already holds — about ten seconds of a run
        somebody is watching, to learn nothing."""
        plant_id = self._plant(db, owner)

        state = service.state_for(
            StartRequest(images=sample_images, location_kind="outdoor", plant_id=plant_id)
        )

        assert state.species is not None
        assert state.species.common_name == "Fragaria x ananassa"

    def test_a_plant_that_was_never_identified_is_identified_now(
        self, service, db, owner, sample_images
    ):
        """Left unset rather than filled with a placeholder: the placeholder satisfies both
        the node's guard and the router's skip, so such a plant could never acquire a
        species however many times it was re-checked."""
        plant_id = self._plant(db, owner, species=None, species_confidence=None)

        state = service.state_for(
            StartRequest(images=sample_images, location_kind="outdoor", plant_id=plant_id)
        )

        assert state.species is None

    def test_a_first_diagnosis_has_no_plant_to_inherit_from(self, service, sample_images):
        state = service.state_for(
            StartRequest(images=sample_images, location_kind="outdoor", plant_name="New one")
        )

        assert state.location_text is None
