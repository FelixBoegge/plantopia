"""Starting a run, reading one, and being refused one.

The executor is replaced throughout with one that records what it was handed and never
runs it. What the work then does is the worker's business and has its own tests; here the
question is only whether the right work was submitted, and whether the right things were
refused before it was.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import dependencies, errors
from core.config import Settings
from core.cost import UsageSnapshot
from data.models import Run
from data.repositories.usage import UsageRepository
from runs.bus import bus
from runs.executor import QueueFullError
from services import limits
from tests.runs import make_run

PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"pretend pixels" * 200


class RecordingExecutor:
    """Accepts work and never runs it."""

    def __init__(self, *, refuses: bool = False) -> None:
        self.submitted: list = []
        self._refuses = refuses

    def submit(self, work) -> None:
        if self._refuses:
            raise QueueFullError(depth=32, limit=32)
        self.submitted.append(work)

    def shutdown(self) -> None:  # pragma: no cover - never called in these tests
        pass


@pytest.fixture
def executor(client):
    recorder = RecordingExecutor()
    _rewire(client, recorder)
    return recorder


def _rewire(client, recorder):
    """Rebuild the run service around a recording executor.

    The service is what gets overridden, not ``executor_for``: the latter is called by
    ``run_service`` rather than injected into it, so an override of it would be read only
    by a dependency that has already been replaced.
    """
    from data.repositories.plants import PlantRepository
    from data.repositories.runs import RunRepository
    from services.run_service import RunService

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


def _start(client, **overrides):
    data = {"plant_name": "Kitchen basil", "location_kind": "indoor"} | overrides
    return client.post(
        "/api/v1/runs",
        data=data,
        files=[("photographs", ("leaf.png", PNG, "image/png"))],
    )


def _runs(db) -> int:
    return db.scalar(select(func.count()).select_from(Run))


def test_starting_a_run_answers_immediately_with_a_run(client, db, executor):
    response = _start(client)

    assert response.status_code == 202
    body = response.json()
    assert body["id"]
    assert body["status"] in {"queued", "running"}


def test_starting_a_run_returns_no_diagnosis(client, executor):
    """The whole point. A response carrying a result would mean the request waited for it."""
    body = _start(client).json()

    assert body["diagnosis_id"] is None
    assert body["finished_at"] is None


def test_starting_a_run_hands_the_work_to_the_executor(client, executor):
    _start(client)

    assert len(executor.submitted) == 1


def test_the_run_exists_before_the_work_is_submitted(client, db, executor):
    """So a client handed an identifier can always fetch something."""
    run_id = _start(client).json()["id"]

    assert client.get(f"/api/v1/runs/{run_id}").status_code == 200


def test_a_run_can_name_one_of_this_owners_plants(client, seeded, executor):
    response = _start(client, plant_id=str(seeded["plant_id"]))

    assert response.status_code == 202
    assert response.json()["plant_id"] == str(seeded["plant_id"])


def test_a_run_naming_another_owners_plant_is_refused(client, db, other_owner, executor):
    from data.repositories.plants import PlantRepository

    theirs = PlantRepository(db).create(
        other_owner,
        name="Their fern",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=datetime.now(UTC),
    )
    db.commit()

    response = _start(client, plant_id=str(theirs))

    assert response.status_code == 404


def test_a_run_naming_another_owners_plant_creates_nothing(client, db, other_owner, executor):
    from data.repositories.plants import PlantRepository

    theirs = PlantRepository(db).create(
        other_owner,
        name="Their fern",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=datetime.now(UTC),
    )
    db.commit()
    before = _runs(db)

    _start(client, plant_id=str(theirs))

    assert _runs(db) == before
    assert executor.submitted == []


def test_reading_a_run_carries_its_status_and_kind(client, db, executor):
    run_id = _start(client).json()["id"]

    body = client.get(f"/api/v1/runs/{run_id}").json()

    assert body["kind"] == "diagnosis"
    assert body["status"] in {"queued", "running"}
    assert body["created_at"]


def test_a_run_never_exposes_its_thread(client, executor):
    """A thread id is the handle that resumes a paid run and reads its photographs."""
    body = _start(client).json()

    assert "thread_id" not in body
    assert "cancel_requested" not in body


def test_another_owners_run_is_absent_rather_than_forbidden(client, db, other_owner, executor):
    theirs = make_run(db, other_owner)
    db.commit()

    response = client.get(f"/api/v1/runs/{theirs.id}")

    assert response.status_code == 404
    assert response.json()["type"] == errors.TYPE_NOT_FOUND


def test_an_unknown_run_answers_the_same_way(client, db, other_owner, executor):
    """Absent and somebody else's must be indistinguishable."""
    from core.ids import new_id

    theirs = make_run(db, other_owner)
    db.commit()

    forbidden = client.get(f"/api/v1/runs/{theirs.id}")
    unknown = client.get(f"/api/v1/runs/{new_id()}")

    assert forbidden.status_code == unknown.status_code
    assert forbidden.json() == unknown.json()


def test_listing_returns_only_this_owners_runs(client, db, owner, other_owner, executor):
    make_run(db, other_owner)
    db.commit()
    _start(client)

    listed = client.get("/api/v1/runs").json()

    assert len(listed) == 1


def test_listing_puts_the_most_recent_first(client, db, owner, executor):
    now = datetime.now(UTC)
    older = make_run(db, owner, now=now - timedelta(hours=1))
    newer = make_run(db, owner, now=now)
    db.commit()

    listed = client.get("/api/v1/runs").json()

    assert [row["id"] for row in listed] == [str(newer.id), str(older.id)]


def test_a_run_at_the_allowance_is_refused(client, db, owner, api_settings, executor):
    usage = UsageRepository(db)
    for _ in range(api_settings.monthly_run_allowance):
        usage.record(
            owner,
            kind=limits.DIAGNOSIS,
            usage=UsageSnapshot(prompt_tokens=1, completion_tokens=1, cost_usd=0.001),
            succeeded=True,
            now=datetime.now(UTC),
        )
    db.commit()

    response = _start(client)

    assert response.status_code == 429
    assert response.json()["type"] == errors.TYPE_QUOTA_EXCEEDED


def test_a_refused_run_leaves_no_record_and_submits_nothing(
    client, db, owner, api_settings, executor
):
    """A refused run that counted against the allowance would make the second attempt
    refused by the first attempt's failure."""
    usage = UsageRepository(db)
    for _ in range(api_settings.monthly_run_allowance):
        usage.record(
            owner,
            kind=limits.DIAGNOSIS,
            usage=UsageSnapshot(prompt_tokens=1, completion_tokens=1, cost_usd=0.001),
            succeeded=True,
            now=datetime.now(UTC),
        )
    db.commit()
    before = _runs(db)

    _start(client)

    assert _runs(db) == before
    assert executor.submitted == []


def test_the_daily_cap_refuses_every_run(client, db, owner, api_settings, executor):
    UsageRepository(db).record(
        owner,
        kind=limits.DIAGNOSIS,
        usage=UsageSnapshot(
            prompt_tokens=1, completion_tokens=1, cost_usd=api_settings.daily_spend_cap_usd
        ),
        succeeded=True,
        now=datetime.now(UTC),
    )
    db.commit()

    response = _start(client)

    assert response.status_code == 503
    assert response.json()["type"] == errors.TYPE_DAILY_CAP


def test_a_full_queue_is_its_own_refusal(client, db, executor):
    """The only one of the three that clears on its own, so the only one where "try again
    shortly" is the right thing to say."""
    refusing = RecordingExecutor(refuses=True)
    _rewire(client, refusing)

    response = _start(client)

    assert response.status_code == 503
    assert response.json()["type"] == errors.TYPE_BUSY
    assert response.headers["Retry-After"] == "60"


def test_a_photograph_that_is_not_an_image_is_refused(client, db, executor):
    before = _runs(db)

    response = client.post(
        "/api/v1/runs",
        data={"plant_name": "Basil", "location_kind": "indoor"},
        files=[("photographs", ("notes.txt", b"this is not a photograph", "text/plain"))],
    )

    assert response.status_code == 400
    assert _runs(db) == before


def test_starting_a_run_without_a_photograph_is_refused(client, db, executor):
    before = _runs(db)

    response = client.post("/api/v1/runs", data={"plant_name": "Basil", "location_kind": "indoor"})

    assert response.status_code == 422
    assert _runs(db) == before


def test_starting_a_run_without_a_session_is_refused(db, api_settings):
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app(api_settings)
    app.dependency_overrides[dependencies.session_dep] = lambda: db
    app.dependency_overrides[dependencies.settings_dep] = lambda: api_settings

    with TestClient(app) as stranger:
        response = stranger.post(
            "/api/v1/runs",
            data={"plant_name": "Basil", "location_kind": "indoor"},
            files=[("photographs", ("leaf.png", PNG, "image/png"))],
        )

    assert response.status_code == 401


class TestTheSpeciesSomebodyTyped:
    """Optional, and optional in both directions: supplying it must work, and omitting it
    must leave the request exactly as it was before the field existed."""

    def test_a_run_starts_with_a_species(self, client, executor):
        response = _start(client, stated_species="Ocimum basilicum")

        assert response.status_code == 202

    def test_a_run_starts_without_one(self, client, executor):
        response = _start(client)

        assert response.status_code == 202

    def test_a_blank_species_is_refused_entry(self, client, executor, monkeypatch):
        """A form sends an empty string for a field somebody left alone. Carried through, it
        would lead the candidates with nothing at all.

        Asserted at the router because that is where the stripping happens; that the value
        then reaches the graph is `tests/unit/services/test_run_service.py`.
        """
        seen = []
        from services.run_service import RunService

        original = RunService.start
        monkeypatch.setattr(
            RunService,
            "start",
            lambda self, request: seen.append(request) or original(self, request),
        )

        _start(client, stated_species="   ")

        assert seen[0].stated_species is None

    def test_a_species_reaches_the_service(self, client, executor, monkeypatch):
        seen = []
        from services.run_service import RunService

        original = RunService.start
        monkeypatch.setattr(
            RunService,
            "start",
            lambda self, request: seen.append(request) or original(self, request),
        )

        _start(client, stated_species="Ocimum basilicum")

        assert seen[0].stated_species == "Ocimum basilicum"
