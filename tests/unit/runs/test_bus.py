"""Fan-out from a run to whoever is watching it.

The property that carries the most weight is the one about a subscriber who has stopped
reading: the worker publishing an event is between two nodes of somebody's diagnosis, and a
closed tab must not be able to hold that up.
"""

import threading

from core.ids import new_id
from runs.bus import SUBSCRIBER_BACKLOG, Event, EventBus


def _event(run_id, sequence=1, kind="step", **payload):
    return Event(run_id=run_id, sequence=sequence, kind=kind, payload=payload or {"n": sequence})


def test_a_subscriber_receives_what_is_published_for_its_run():
    bus = EventBus()
    run = new_id()
    watcher = bus.subscribe(run)

    bus.publish(_event(run))

    received = watcher.next(timeout=1.0)
    assert received is not None
    assert received.sequence == 1


def test_two_subscribers_to_one_run_both_receive():
    """A person with the page open twice, or two devices. Neither may starve the other."""
    bus = EventBus()
    run = new_id()
    first, second = bus.subscribe(run), bus.subscribe(run)

    delivered = bus.publish(_event(run))

    assert delivered == 2
    assert first.next(timeout=1.0).sequence == 1
    assert second.next(timeout=1.0).sequence == 1


def test_a_subscriber_to_another_run_receives_nothing():
    bus = EventBus()
    mine, theirs = new_id(), new_id()
    watcher = bus.subscribe(theirs)

    bus.publish(_event(mine))

    assert watcher.next(timeout=0.05) is None


def test_publishing_to_a_run_nobody_watches_is_not_an_error():
    """The common case, in fact: a run started from a script, or watched only after it
    finished. It must not be the worker's problem."""
    bus = EventBus()

    assert bus.publish(_event(new_id())) == 0


def test_events_arrive_in_the_order_they_were_published():
    bus = EventBus()
    run = new_id()
    watcher = bus.subscribe(run)

    for sequence in range(1, 6):
        bus.publish(_event(run, sequence))

    assert [watcher.next(timeout=1.0).sequence for _ in range(5)] == [1, 2, 3, 4, 5]


def test_a_subscriber_that_stopped_reading_does_not_block_a_publish():
    """The one that matters. A closed tab whose connection has not noticed yet would
    otherwise hold up a worker mid-diagnosis, for every run it was watching.
    """
    bus = EventBus()
    run = new_id()
    bus.subscribe(run)  # subscribed, never read from

    finished = threading.Event()

    def _publish_far_more_than_it_can_hold():
        for sequence in range(SUBSCRIBER_BACKLOG * 2):
            bus.publish(_event(run, sequence))
        finished.set()

    threading.Thread(target=_publish_far_more_than_it_can_hold, daemon=True).start()

    assert finished.wait(timeout=5.0), "publishing blocked on a subscriber that stopped reading"


def test_a_dropped_event_is_reported_rather_than_silent(caplog):
    """It is still in the database and a reconnect replays it — but a bus quietly losing
    events with nothing in the log is a bus nobody can debug."""
    import logging

    bus = EventBus()
    run = new_id()
    bus.subscribe(run)

    with caplog.at_level(logging.WARNING, logger="runs.bus"):
        for sequence in range(SUBSCRIBER_BACKLOG + 5):
            bus.publish(_event(run, sequence))

    assert "dropped event" in caplog.text


def test_unsubscribing_stops_delivery():
    bus = EventBus()
    run = new_id()
    watcher = bus.subscribe(run)

    bus.unsubscribe(watcher)
    delivered = bus.publish(_event(run))

    assert delivered == 0


def test_unsubscribing_wakes_the_reader():
    """Otherwise a handler whose client went away waits for an event that will never come,
    holding a connection and a thread until something times out."""
    bus = EventBus()
    run = new_id()
    watcher = bus.subscribe(run)

    bus.unsubscribe(watcher)

    assert watcher.next(timeout=1.0) is None


def test_unsubscribing_the_last_watcher_forgets_the_run():
    """A long-lived process would otherwise accumulate one empty set per run it ever
    served."""
    bus = EventBus()
    run = new_id()
    watcher = bus.subscribe(run)

    bus.unsubscribe(watcher)

    assert bus.watched_runs == 0


def test_unsubscribing_one_of_two_leaves_the_other(caplog):
    bus = EventBus()
    run = new_id()
    leaving, staying = bus.subscribe(run), bus.subscribe(run)

    bus.unsubscribe(leaving)

    assert bus.publish(_event(run)) == 1
    assert staying.next(timeout=1.0).sequence == 1


def test_closing_a_run_wakes_every_watcher():
    """A finished run has to tell its watchers so, or each of them waits out its own
    timeout on a stream that will never say anything again."""
    bus = EventBus()
    run = new_id()
    first, second = bus.subscribe(run), bus.subscribe(run)

    bus.close_run(run)

    assert first.next(timeout=1.0) is None
    assert second.next(timeout=1.0) is None
    assert bus.watched_runs == 0


def test_a_publish_after_a_run_is_closed_reaches_nobody():
    bus = EventBus()
    run = new_id()
    bus.subscribe(run)

    bus.close_run(run)

    assert bus.publish(_event(run)) == 0


def test_next_returns_nothing_when_no_event_arrives():
    """A quiet run is not a finished one. The caller distinguishes them by reading the
    status, which is why both answer the same way here."""
    bus = EventBus()
    watcher = bus.subscribe(new_id())

    assert watcher.next(timeout=0.05) is None
