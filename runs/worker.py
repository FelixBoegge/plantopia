"""What happens on the pool's thread.

**This module owns the graph's generators; the SSE handler owns the connection.** They meet
at the bus and nowhere else, and that indirection is load-bearing rather than tidy. A spike
established why: `graph.stream(...)` *ends* at the interrupt. A handler streaming the
generator straight to the response would close the connection halfway through every
diagnosis that stops to ask a question — which is all of them. Here, the pause is two
submissions to the pool, and to a watcher it is simply a gap between two publishes.

**A run's session belongs to the run.** The request that started it is long gone by the
time this executes, and its session with it. Each pass opens its own and closes it.

**Every exit records what was spent.** Completed, failed or cancelled: the money left when
the model was called, not when a result arrived, and a quota that only sees successes is
one somebody can exhaust by failing.
"""

import logging
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

from langgraph.types import Command

from agent.wiring import build_deps, open_session
from core.config import Settings
from core.cost import UsageCollector
from data.engine import transaction
from data.repositories import runs as run_status
from data.repositories.runs import RunRepository
from data.repositories.usage import UsageRepository
from runs import steps
from runs.bus import Event, EventBus
from services import limits

logger = logging.getLogger(__name__)

# What a client is told when a run fails. Deliberately the same sentence whatever broke:
# an exception message can carry a query, a filename, or a fragment of somebody's data.
FAILURE = "The run could not be completed. Nothing was saved; you can try again."
TIMED_OUT = "The run stopped responding and was ended. You can try again."


class RunCancelledError(Exception):
    """Raised inside the stream loop when a stop has been asked for.

    An exception rather than a return, because it has to unwind out of the middle of a
    generator that is otherwise going to keep producing nodes.
    """


def execute(
    *,
    run_id: UUID,
    user_id: UUID,
    thread_id: str,
    initial_state,
    settings: Settings,
    bus: EventBus,
    resume=None,
    session_factory=None,
    build_graph=None,
) -> None:
    """Drive one pass of a run: from the start, or from where it paused.

    Called on a pool thread. Never raises: a failure here has nowhere to go but a log, so
    it becomes a ``failed`` run and a terminal event instead.

    ``session_factory`` and ``build_graph`` default to the real thing and exist to be
    replaced. They are not test scaffolding bolted on: they are the same two seams a real
    worker process would need, and having them means this function can be driven end to
    end against scripted models without a single patch.
    """
    session = (session_factory or (lambda: open_session(settings)))()
    runs = RunRepository(session)
    collector = UsageCollector()

    try:
        now = datetime.now(UTC)
        # ``queued`` for both a first pass and a resume: the service moves a run there
        # before submitting either, so that a client polling between the request and the
        # worker picking it up sees a real state rather than a stale one. Expecting
        # ``awaiting_answers`` on the resume path looked right and meant no resumed run ever
        # started — it sat queued until the sweeper failed it. Found by walking the README
        # against a running server; neither side's unit tests could see it, because each
        # was correct about its own half.
        started = runs.advance(run_id, expected=run_status.QUEUED, to=run_status.RUNNING, now=now)
        session.commit()
        if not started:
            # Cancelled between being queued and being picked up, or answered twice. The
            # run is somebody else's business now.
            logger.info("run %s was not in a state to start; leaving it alone", run_id)
            return

        _drive(
            run_id=run_id,
            user_id=user_id,
            thread_id=thread_id,
            initial_state=initial_state,
            resume=resume,
            settings=settings,
            session=session,
            runs=runs,
            bus=bus,
            collector=collector,
            build_graph=build_graph,
        )
    except RunCancelledError:
        _finish(
            runs, session, bus, run_id, to=run_status.CANCELLED, kind=steps.CANCELLED, detail={}
        )
    except Exception:
        logger.exception("run %s failed", run_id)
        _finish(
            runs,
            session,
            bus,
            run_id,
            to=run_status.FAILED,
            kind=steps.FAILED,
            detail={"detail": FAILURE},
            error=FAILURE,
        )
    finally:
        _record_usage(session, runs, run_id=run_id, user_id=user_id, collector=collector)
        session.close()


def _drive(
    *,
    run_id: UUID,
    user_id: UUID,
    thread_id: str,
    initial_state,
    resume,
    settings: Settings,
    session,
    runs: RunRepository,
    bus: EventBus,
    collector: UsageCollector,
    build_graph=None,
) -> None:
    """One pass of the graph, publishing as it goes."""
    graph = (build_graph or _real_graph)(session=session, user_id=user_id, settings=settings)

    config = {
        "configurable": {"thread_id": thread_id, "usage_collector": collector},
        "callbacks": [collector],
    }
    payload = Command(resume=resume) if resume is not None else initial_state

    interrupted = False
    # Wall-time between publishes, which includes the graph's own overhead between nodes.
    # That is why the client says "took 4.1s" rather than presenting it as model latency:
    # it is how long the step took, not how long the model thought.
    mark = monotonic()
    for update in graph.stream(payload, config, stream_mode="updates"):
        if runs.cancel_requested(run_id):
            raise RunCancelledError

        for node, value in update.items():
            if node == "__interrupt__":
                interrupted = True
                _pause(runs, session, bus, run_id, value)
                break
            now = monotonic()
            _publish_step(
                runs,
                session,
                bus,
                run_id,
                node,
                settings=settings,
                duration_ms=int((now - mark) * 1000),
            )
            mark = now

        if interrupted:
            return

    _complete(runs, session, bus, run_id, graph=graph, config=config)


def _real_graph(*, session, user_id: UUID, settings: Settings):
    """The diagnosis graph, on this run's session and this owner's profile.

    Built per run rather than per process: it closes over repositories bound to a session,
    and a session outlives neither the run nor the thread it belongs to.
    """
    from agent.checkpoints import build_checkpointer, checkpointer_url
    from agent.diagnosis_graph import build_diagnosis_graph

    deps = build_deps(
        user_id=user_id,
        profile_facts=_profile_facts(session, user_id),
        settings=settings,
        session=session,
    )
    return build_diagnosis_graph(deps, build_checkpointer(checkpointer_url(settings)))


def _publish_step(
    runs, session, bus, run_id, node: str, *, settings: Settings, duration_ms: int
) -> None:
    """Record one node's completion, then tell whoever is watching.

    Persisted first, always. Publishing first would mean a client receiving an event the
    database does not have, and a reconnect replaying a shorter history than the one
    already on screen.

    `calls` is omitted where the node reached for nothing outside the process, rather than
    sent empty: a client renders the key when it is present, and an empty one would draw a
    blank line where a sentence belongs.
    """
    step = steps.step_for(node)
    payload = {"step": step.id, "description": step.description, "duration_ms": duration_ms}
    calls = steps.calls_for(node, settings)
    if calls is not None:
        payload["calls"] = calls
    with transaction(session):
        sequence = runs.append_event(run_id, kind=steps.STEP, payload=payload, now=_now())
    bus.publish(Event(run_id=run_id, sequence=sequence, kind=steps.STEP, payload=payload))


def _pause(runs, session, bus, run_id, interrupts) -> None:
    """The graph stopped to ask. That is a status, not a failure."""
    asked = _asked(interrupts)

    # Everything the pause carries, passed through rather than named here. This was a
    # whitelist of two keys, and the first key added to the interrupt afterwards — the
    # staleness threshold — was silently dropped: the graph sent it, every test on either
    # side agreed it was sent, and the browser never saw it.
    payload = {key: value for key, value in asked.items() if key != "identification"}
    payload.setdefault("questions", [])
    # Absent rather than empty when there is nothing to choose between, so a client can
    # test for the block rather than for the length of it.
    if asked.get("identification"):
        payload["identification"] = asked["identification"]
    with transaction(session):
        runs.advance(
            run_id, expected=run_status.RUNNING, to=run_status.AWAITING_ANSWERS, now=_now()
        )
        sequence = runs.append_event(run_id, kind=steps.QUESTIONS, payload=payload, now=_now())
    bus.publish(Event(run_id=run_id, sequence=sequence, kind=steps.QUESTIONS, payload=payload))


def _complete(runs, session, bus, run_id, *, graph, config) -> None:
    """The graph finished. Record what it produced, or why it produced nothing.

    A run can finish without a diagnosis: the intake guard refuses a photograph that is not
    a plant, or one nothing can be read from. That is not a failure — nothing broke — but a
    client told only ``completed`` with a null diagnosis has been told nothing at all, and
    it is the most likely first thing anybody sees. So the reason travels with the terminal
    event and is recorded on the run.
    """
    state = graph.get_state(config).values
    diagnosis_id = state.get("diagnosis_id")
    # The plant the run worked on, which for a run started without one is the plant its
    # ``persist`` node created. Recorded because a client is otherwise handed a diagnosis
    # and no way to reach the thing it just paid for — it would have to find the plant by
    # guessing from a timestamp.
    plant_id = state.get("plant_id")
    rejected = bool(state.get("rejected"))
    reason = state.get("rejection_reason") if rejected else None

    payload = {
        "diagnosis_id": str(diagnosis_id) if diagnosis_id else None,
        "plant_id": str(plant_id) if plant_id else None,
        "rejected": rejected,
        "reason": reason,
    }

    with transaction(session):
        runs.advance(
            run_id,
            expected=run_status.RUNNING,
            to=run_status.COMPLETED,
            now=_now(),
            diagnosis_id=diagnosis_id,
            plant_id=plant_id,
            error=reason,
        )
        sequence = runs.append_event(run_id, kind=steps.COMPLETED, payload=payload, now=_now())
    bus.publish(Event(run_id=run_id, sequence=sequence, kind=steps.COMPLETED, payload=payload))
    bus.close_run(run_id)


def _finish(runs, session, bus, run_id, *, to: str, kind: str, detail: dict, error=None) -> None:
    """End a run that did not finish on its own, and say so on the stream.

    Rolls back first: whatever was in flight when this was reached is not something to
    commit alongside the failure.
    """
    session.rollback()
    with transaction(session):
        moved = runs.advance(run_id, expected=run_status.UNFINISHED, to=to, now=_now(), error=error)
        sequence = runs.append_event(run_id, kind=kind, payload=detail, now=_now()) if moved else 0
    if moved:
        bus.publish(Event(run_id=run_id, sequence=sequence, kind=kind, payload=detail))
    bus.close_run(run_id)


def _record_usage(session, runs, *, run_id: UUID, user_id: UUID, collector) -> None:
    """Account for what this pass spent: carry it forward, or record the run's total.

    One ledger entry per run, claimed conditionally so a worker finishing and the sweeper
    giving up on the same run cannot both record it — which would charge an owner twice
    for one diagnosis.

    **A pass that did not finish the run carries its spend forward instead.** This is
    where the accounting used to lose money. A diagnosis pauses at the clarifying-question
    interrupt, and every pass builds its own collector, so the pass that finishes knows
    only what *it* spent — while the vision and gate calls, the expensive ones, all
    happened before the pause. This function used to return early on a non-terminal
    status, on the belief that the collector spanned the whole thread; it never did, and
    so every interrupted diagnosis was charged at roughly half price against the owner's
    quota and the daily spend cap.

    So the pause writes its snapshot to the run, and the pass that finishes adds it to its
    own. The total is the only figure that reaches the ledger.
    """
    snapshot = collector.snapshot()
    try:
        session.rollback()
        with transaction(session):
            status = runs.status_of(run_id)
            if status not in run_status.TERMINAL:
                # Not finished, so nothing to charge yet — but this pass's spend has to
                # outlive the worker thread that made it, and the pause can outlive the
                # process.
                runs.add_partial_usage(run_id, snapshot)
                return
            if not runs.mark_usage_recorded(run_id):
                return
            UsageRepository(session).record(
                user_id,
                kind=limits.DIAGNOSIS,
                usage=_total_spend(runs, run_id, snapshot),
                succeeded=status == run_status.COMPLETED,
                now=_now(),
            )
    except Exception:  # pragma: no cover - accounting must never break a finished run
        logger.exception("could not record usage for run %s", run_id)


def _total_spend(runs, run_id: UUID, this_pass):
    """Every pass of this run, added together.

    ``None`` only when no pass reported any usage at all, which is the ordinary case under
    scripted models — a zeroed figure would make a run look measured when it was not.
    """
    carried = runs.partial_usage_of(run_id)
    if this_pass is None:
        return carried
    return this_pass.plus(carried)


def _profile_facts(session, user_id: UUID):
    """The owner's learned profile, rendered for prompts.

    Built here rather than passed in because it belongs to this run's session, which the
    request that started the run does not share. No gate model: rendering existing facts
    reads the table and nothing else — the model is only for deciding what to learn, which
    happens on the chat path.
    """
    from data.repositories.profile import ProfileRepository
    from services.profile_service import ProfileService

    service = ProfileService(
        user_id=user_id, repo=ProfileRepository(session), gate_model=None, now=_now
    )
    return service.facts_for_prompt


def _asked(interrupts) -> dict:
    """What an interrupt is asking for, as plain data.

    The questions, and the identification candidates when there is a decision to make.
    """
    if not interrupts:
        return {}
    value = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
    return value if isinstance(value, dict) else {}


def _now() -> datetime:
    return datetime.now(UTC)
