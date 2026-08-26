"""Watching a run over SSE.

The properties here are about what a client can rely on when the connection is imperfect,
which is the normal case: a reload, a tunnel, a laptop lid. The owner has already paid for
the run and waited for it, so none of those may cost them the result.

Events are published straight to the bus in most of these rather than by running a graph —
what the worker publishes has its own tests, and mixing the two would make a streaming bug
and a graph bug look alike.
"""

import json
import threading
import time
from datetime import UTC, datetime

import pytest

from api import dependencies
from core.config import Settings
from core.ids import new_id
from data.repositories.runs import RunRepository
from runs import steps
from runs.bus import Event, bus
from tests.runs import make_run
from tests.secrets import TEST_JWT_SECRET

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _a_quiet_bus():
    """The bus is process-wide. A run left watched by one test would receive another's."""
    yield
    for run_id in list(bus._subscribers):  # noqa: SLF001 — test teardown, not behaviour
        bus.close_run(run_id)


@pytest.fixture
def api_settings():
    """A one-second keep-alive.

    Two reasons, and both are about this file. It is what makes the keep-alive assertion
    take a second rather than fifteen; and it is what gives the reading loop control often
    enough that a stream which never closes fails on its deadline instead of hanging.
    """
    return Settings(
        _env_file=None,
        openrouter_api_key="sk-test",
        jwt_secret=TEST_JWT_SECRET,
        secure_cookies=False,
        run_keepalive_seconds=1,
    )


@pytest.fixture
def run(db, owner):
    record = make_run(db, owner)
    run_id = record.id
    db.commit()
    return run_id


def _record(db, run_id, kind, payload, *, publish=True):
    """Store an event the way the worker does. Used for what exists *before* a stream opens.

    Writes only from the test's own thread. The test session lives inside a transaction
    that never really commits, so a second connection cannot see this run at all — which
    is why the live half of these tests publishes to the bus and does not write.
    """
    sequence = RunRepository(db).append_event(
        run_id, kind=kind, payload=payload, now=datetime.now(UTC)
    )
    db.commit()
    if publish:
        bus.publish(Event(run_id=run_id, sequence=sequence, kind=kind, payload=payload))
    return sequence


def _publish(run_id, kind, payload, sequence):
    """Announce an event without storing it.

    What a watcher receives live comes from the bus and nowhere else, so a streaming test
    does not need a row — and writing one from another thread would need a connection that
    cannot see this run.
    """
    bus.publish(Event(run_id=run_id, sequence=sequence, kind=kind, payload=payload))


def _parse(lines):
    """The event stream's framing, as a client sees it. Comment lines are not events."""
    received, event, data = [], None, None
    for line in lines:
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = line.split(":", 1)[1].strip()
        elif line == "" and event is not None:
            received.append((event, json.loads(data) if data else None))
            event, data = None, None
    return received


def _read(client, run_id, *, headers=None, limit=None, deadline=8.0):
    """Read a stream to its close, or until ``limit`` events, or until time runs out.

    The deadline matters. A stream that never closes is a real failure mode here — it is
    what a lost event looks like — and without a bound the test hangs instead of failing,
    which in CI spends the whole job rather than reporting in a second.
    """
    received = []
    expires = time.monotonic() + deadline
    with client.stream(
        "GET", f"/api/v1/runs/{run_id}/events", headers=headers or {}, timeout=deadline
    ) as response:
        assert response.status_code == 200, response.status_code

        # The deadline below is checked between lines, and `iter_lines` blocks *on* a line
        # that may never come — so on its own it does not bound anything. It looked like it
        # did: the check inside the loop is the obvious reading, and the case it was written
        # for (a lost event) is exactly the case where the loop never gets another
        # iteration. Closing the response from a timer is what actually ends the read.
        watchdog = threading.Timer(deadline, response.close)
        watchdog.daemon = True
        watchdog.start()
        event, data = None, None
        for line in response.iter_lines():
            if time.monotonic() > expires:
                break
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
            elif line == "" and event is not None:
                received.append((event, json.loads(data) if data else None))
                event, data = None, None
                if limit and len(received) >= limit:
                    break
        watchdog.cancel()
    return received


def _wait_for_a_watcher(timeout=10.0):
    """Block until the stream handler has subscribed, or give up.

    Giving up rather than waiting for ever: if the subscription never appears the test
    should fail on its assertion about what arrived, which says what went wrong, rather
    than stopping here, which says only that something did.
    """
    expires = time.monotonic() + timeout
    while bus.watched_runs == 0 and time.monotonic() < expires:
        time.sleep(0.01)


def test_a_finished_run_replays_from_the_beginning_and_closes(client, db, run):
    """No waiting for events that will never come."""
    _record(db, run, steps.STEP, {"step": "checking", "description": "Checking"})
    _record(db, run, steps.COMPLETED, {"diagnosis_id": None})

    received = _read(client, run)

    assert [kind for kind, _ in received] == [steps.STEP, steps.COMPLETED]


def test_the_stream_carries_the_sequence_as_the_event_id(client, db, run):
    """A browser echoes it back as `Last-Event-ID`, so the whole replay rests on it."""
    _record(db, run, steps.COMPLETED, {"diagnosis_id": None})

    with client.stream("GET", f"/api/v1/runs/{run}/events", timeout=10.0) as response:
        body = "".join(response.iter_text())

    assert "id: 1" in body


def test_reconnecting_receives_only_what_was_missed(client, db, run):
    for index in range(3):
        _record(db, run, steps.STEP, {"step": f"s{index}", "description": "Working"})
    _record(db, run, steps.COMPLETED, {"diagnosis_id": None})

    received = _read(client, run, headers={"Last-Event-ID": "2"})

    assert [payload.get("step") for _, payload in received if payload.get("step")] == ["s2"]


def test_a_reconnect_naming_an_unknown_sequence_gets_everything(client, db, run):
    """Nonsense from a browser is read conservatively: send it all rather than nothing."""
    _record(db, run, steps.COMPLETED, {"diagnosis_id": None})

    received = _read(client, run, headers={"Last-Event-ID": "not-a-number"})

    assert len(received) == 1


def test_a_run_still_working_streams_events_as_they_are_published(client, db, owner, run):
    """The live half: the client is connected before anything happens."""

    def _work():
        # Waits for the subscription rather than sleeping a guessed interval. A fixed sleep
        # is a bet that the connection is established by then, and under coverage — which
        # slows every instrumented line — it is a bet that loses: the events are published
        # to nobody, the client waits for events that already happened, and the whole suite
        # hangs rather than failing.
        _wait_for_a_watcher()
        _publish(run, steps.STEP, {"step": "identifying", "description": "Looking"}, 1)
        _publish(run, steps.COMPLETED, {"diagnosis_id": None}, 2)

    threading.Thread(target=_work, daemon=True).start()

    received = _read(client, run)

    assert [kind for kind, _ in received] == [steps.STEP, steps.COMPLETED]


def test_an_event_published_while_connecting_is_not_lost(client, db, owner, run, api_settings):
    """Subscribing happens before the replay for exactly this.

    Made deterministic rather than raced for: the replay itself publishes. An event that
    arrives while the stored history is being read can only be seen by a subscription that
    already existed, so this either passes for the right reason or hangs — and a racing
    version of it would pass for the wrong one most of the time.
    """
    _record(db, run, steps.STEP, {"step": "checking", "description": "Checking"})

    from data.repositories.plants import PlantRepository
    from data.repositories.runs import RunRepository
    from data.repositories.usage import UsageRepository
    from services.run_service import RunService

    class _PublishingWhileReplaying(RunService):
        def events(self, run_id, *, after=0):
            stored = super().events(run_id, after=after)
            _publish(run_id, steps.COMPLETED, {"diagnosis_id": None}, 2)
            return stored

    client.app.dependency_overrides[dependencies.run_service] = lambda: _PublishingWhileReplaying(
        user_id=owner,
        tier="free",
        runs=RunRepository(db),
        plants=PlantRepository(db),
        usage=UsageRepository(db),
        executor=None,
        bus=bus,
        settings=api_settings,
        now=lambda: datetime.now(UTC),
    )

    received = _read(client, run)

    assert [kind for kind, _ in received] == [steps.STEP, steps.COMPLETED]


def test_an_event_covered_by_the_replay_is_not_sent_twice(client, db, run):
    """Subscribing first makes duplicates possible; the sequence is what settles them."""
    step = {"step": "checking", "description": "Checking"}
    sequence = _record(db, run, steps.STEP, step, publish=False)

    def _work():
        _wait_for_a_watcher()
        _publish(run, steps.STEP, step, sequence)  # the duplicate
        _publish(run, steps.COMPLETED, {"diagnosis_id": None}, sequence + 1)

    threading.Thread(target=_work, daemon=True).start()

    received = _read(client, run)

    assert [kind for kind, _ in received].count(steps.STEP) == 1


def test_the_stream_survives_the_pause_for_questions(client, db, run):
    """One connection spans both halves of a run. The pause is a gap between publishes."""

    def _work():
        # Waits for the watcher rather than sleeping towards it. The gap in the middle is
        # the pause itself and only needs to be non-zero; the one at the start was a guess
        # about when the connection would be up, and a guess that is wrong publishes to
        # nobody and hangs the read.
        _wait_for_a_watcher()
        _publish(run, steps.STEP, {"step": "checking", "description": "Checking"}, 1)
        _publish(run, steps.QUESTIONS, {"questions": [{"key": "watering"}]}, 2)
        time.sleep(0.05)  # the person reading their screen
        _publish(run, steps.STEP, {"step": "diagnosing", "description": "Weighing"}, 3)
        _publish(run, steps.COMPLETED, {"diagnosis_id": None}, 4)

    threading.Thread(target=_work, daemon=True).start()

    received = _read(client, run)

    assert [kind for kind, _ in received] == [
        steps.STEP,
        steps.QUESTIONS,
        steps.STEP,
        steps.COMPLETED,
    ]


def test_a_failed_run_ends_the_stream_with_a_statement(client, db, run):
    """A connection that simply stops is indistinguishable from a network failure."""
    _record(db, run, steps.FAILED, {"detail": "The run could not be completed."})

    received = _read(client, run)

    assert received[-1][0] == steps.FAILED


def test_a_cancelled_run_ends_the_stream_with_a_statement(client, db, run):
    _record(db, run, steps.CANCELLED, {})

    received = _read(client, run)

    assert received[-1][0] == steps.CANCELLED


def test_another_owners_stream_is_absent(client, db, other_owner):
    theirs = make_run(db, other_owner)
    run_id = theirs.id
    db.commit()
    _record(db, run_id, steps.COMPLETED, {"diagnosis_id": None})

    response = client.get(f"/api/v1/runs/{run_id}/events")

    assert response.status_code == 404


def test_another_owners_stream_delivers_nothing(client, db, other_owner):
    theirs = make_run(db, other_owner)
    run_id = theirs.id
    db.commit()
    _record(db, run_id, steps.STEP, {"step": "checking", "description": "Checking"})

    response = client.get(f"/api/v1/runs/{run_id}/events")

    assert "checking" not in response.text


def test_an_unknown_run_answers_like_another_owners(client, db, other_owner):
    theirs = make_run(db, other_owner)
    run_id = theirs.id
    db.commit()

    forbidden = client.get(f"/api/v1/runs/{run_id}/events")
    unknown = client.get(f"/api/v1/runs/{new_id()}/events")

    assert forbidden.status_code == unknown.status_code
    assert forbidden.json() == unknown.json()


def test_a_stream_hands_its_database_connection_back_before_streaming(client, db, run):
    """A stream lives for minutes. One pooled connection per watcher, on top of one per
    running diagnosis, is how a deployment runs out of database connections rather than
    out of workers.

    The session override is a plain function with no teardown, so any close during the
    request is the endpoint's own.
    """
    _record(db, run, steps.COMPLETED, {"diagnosis_id": None})
    closes = []
    original_close = db.close

    def _counting_close():
        closes.append(True)
        original_close()

    db.close = _counting_close
    try:
        _read(client, run)
    finally:
        db.close = original_close

    assert closes, "the endpoint held its session for the life of the stream"


def test_the_stream_is_configured_to_keep_itself_alive(client, db, run, api_settings):
    """A run can spend a minute inside one model call, and intermediaries close connections
    that look idle — so an idle stream has to say something.

    The interval is asserted, not the emission. Keep-alive comes from ``sse_starlette``'s
    own ping task, and this project's `TestClient` does not surface those comment lines
    through a streaming response no matter how the handler is arranged; a test that tried
    hung rather than failed. What is checked here is the half this code owns: that the
    configured interval reaches the response. `M31` records the rest.
    """
    from api import streaming

    captured = {}

    class _Capturing(streaming.EventSourceResponse):
        def __init__(self, content, **kwargs):
            captured.update(kwargs)
            super().__init__(content, **kwargs)

    original = streaming.EventSourceResponse
    streaming.EventSourceResponse = _Capturing
    try:
        _record(db, run, steps.COMPLETED, {"diagnosis_id": None})
        _read(client, run)
    finally:
        streaming.EventSourceResponse = original

    assert captured["ping"] == api_settings.run_keepalive_seconds


def test_keep_alive_traffic_would_not_be_delivered_as_an_event(client, db, run):
    """A comment line, not an event. `sse_starlette` writes pings as `: ...`, which the
    parser in this file ignores by construction — asserted so that a change to how events
    are framed cannot quietly turn pings into visible activity.
    """
    parsed = _parse([": ping - 2026-01-01", "", "event: step", "data: {}", ""])

    assert parsed == [("step", {})]


def test_the_replay_read_leaves_the_event_loop(run):
    """The one blocking thing a stream does is read stored events, and it is a database
    call. Run on the loop it would stall every request in the process for its duration —
    the failure that looks like the whole application hanging under a load nobody would
    call load.

    Asserted by running ``stream_run`` directly rather than through a client: `TestClient`
    serves one request at a time, so a concurrency test written against it would be
    asserting `TestClient`.
    """
    import asyncio

    from api import streaming
    from runs.bus import EventBus

    ran_on = {}

    def _replay(after):
        ran_on["thread"] = threading.current_thread().name
        return []

    async def _drive():
        ran_on["loop"] = threading.current_thread().name
        response = await streaming.stream_run(
            request=_NeverDisconnected(),
            run_id=run,
            bus=EventBus(),
            replay=_replay,
            after=0,
            keepalive_seconds=15,
        )
        assert response is not None

    asyncio.run(_drive())

    assert ran_on["thread"] != ran_on["loop"], "the replay read ran on the event loop"


class _NeverDisconnected:
    """The smallest thing ``stream_run`` needs from a request."""

    async def is_disconnected(self) -> bool:
        return False
