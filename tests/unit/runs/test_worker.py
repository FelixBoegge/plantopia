"""A whole run, driven end to end against scripted models.

No LLM call, no network, and no patching: the worker takes its session and its graph as
arguments, which is the same seam a real worker process would need.

This is where the spike's finding is held. The graph's generator ends at the interrupt, so
the pause here is two calls to ``execute`` — and everything a client sees of it comes from
the bus, which is what lets one connection span both.
"""

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select

from agent.diagnosis_graph import build_diagnosis_graph
from agent.state import DiagnosisState
from agent.threads import diagnosis_thread
from core.config import Settings
from core.cost import UsageSnapshot
from data.models import UsageEvent
from data.repositories import runs as run_status
from data.repositories.runs import RunRepository
from runs import steps, sweeper, worker
from runs.bus import EventBus
from tests.runs import make_run
from tests.secrets import TEST_JWT_SECRET

ANSWERS = {"watering": "every other day", "drainage": "No drainage holes"}


@pytest.fixture
def settings():
    return Settings(_env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET)


@pytest.fixture
def scripted_graph(make_deps, pipeline_models):
    """A real diagnosis graph with scripted models behind it.

    In-memory checkpointer: these runs pause and resume within one test, and a Postgres
    checkpoint per test would be litter with no reader.
    """
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    graph = build_diagnosis_graph(deps, MemorySaver())

    def _build(**_):
        return graph

    return _build


@pytest.fixture
def bus():
    return EventBus()


@dataclass(frozen=True)
class _Started:
    """A run, as plain values.

    Deliberately not the ORM object. The worker owns the session it is given and rolls it
    back on a failure, which expires every instance attached to it — so a test holding a
    ``Run`` across ``execute`` reads a detached one afterwards, and fails for a reason that
    has nothing to do with what it was asserting.
    """

    id: object
    user_id: object
    thread_id: str


def _run_and_state(db, owner, sample_images, *, status=None):
    thread_id = diagnosis_thread(owner)
    run = make_run(db, owner, status=status or run_status.QUEUED, thread_id=thread_id)
    started = _Started(id=run.id, user_id=run.user_id, thread_id=run.thread_id)
    db.commit()
    state = DiagnosisState(images=sample_images, plant_name="Kitchen basil", location_kind="indoor")
    return started, state


def _execute(run, state, *, settings, bus, graph, db, resume=None):
    if resume is not None:
        # What ``RunService.answer`` does before submitting. Driving ``execute`` without it
        # would test a state the application never produces.
        RunRepository(db).advance(
            run.id,
            expected=run_status.AWAITING_ANSWERS,
            to=run_status.QUEUED,
            now=datetime.now(UTC),
        )
        db.commit()
    worker.execute(
        run_id=run.id,
        user_id=run.user_id,
        thread_id=run.thread_id,
        initial_state=state,
        settings=settings,
        bus=bus,
        resume=resume,
        session_factory=lambda: db,
        build_graph=graph,
    )


def test_a_run_reaches_the_interrupt_and_waits(
    db, owner, sample_images, settings, bus, scripted_graph
):
    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    assert RunRepository(db).get(owner, run.id).status == run_status.AWAITING_ANSWERS


def test_the_pause_carries_the_questions(db, owner, sample_images, settings, bus, scripted_graph):
    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    events = RunRepository(db).events(owner, run.id)
    asking = [event for event in events if event.kind == steps.QUESTIONS]
    assert len(asking) == 1
    assert {question["key"] for question in asking[0].payload["questions"]} >= {"watering"}


def test_the_pause_carries_everything_the_graph_put_in_it(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """This was a whitelist of two keys, and the third key the graph started sending was
    dropped here without a word: the graph sent it, the graph's own tests agreed it was
    sent, the client read for it, and the browser never saw it.

    Asserted against the interrupt rather than against a list of names, so the next key
    added does not need this test edited to survive the trip.
    """
    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    events = RunRepository(db).events(owner, run.id)
    asking = [event for event in events if event.kind == steps.QUESTIONS][0]

    assert asking.payload["stale_after_days"] == settings.stale_photograph_days


def test_answering_completes_the_run(db, owner, sample_images, settings, bus, scripted_graph):
    """The second pass, which the spike proved continues the same thread rather than
    starting again."""
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    finished = RunRepository(db).get(owner, run.id)
    assert finished.status == run_status.COMPLETED
    assert finished.diagnosis_id is not None
    assert finished.finished_at is not None


def test_a_completed_run_names_the_diagnosis_it_produced(
    db, owner, sample_images, settings, bus, scripted_graph
):
    from data.models import Diagnosis

    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    diagnosis_id = RunRepository(db).get(owner, run.id).diagnosis_id
    assert db.get(Diagnosis, diagnosis_id) is not None


def test_every_step_becomes_an_event(db, owner, sample_images, settings, bus, scripted_graph):
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    events = RunRepository(db).events(owner, run.id)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert events[-1].kind == steps.COMPLETED


def _steps_of(db, owner, run):
    return [
        event.payload
        for event in RunRepository(db).events(owner, run.id)
        if event.kind == steps.STEP
    ]


def test_a_step_says_what_it_called(db, owner, sample_images, settings, bus, scripted_graph):
    """The screen names the model. It can only do that if the event does."""
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    identifying = [p for p in _steps_of(db, owner, run) if p["step"] == "identifying"]

    assert identifying, "the run never reached the identification step"
    assert "via OpenRouter" in identifying[0]["calls"]


def test_a_step_that_calls_nothing_carries_no_calls_key(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """Absent, not empty. A client renders the key when it is there, and an empty string
    would draw a blank line where a sentence goes."""
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    saving = [p for p in _steps_of(db, owner, run) if p["step"] == "saving"]

    assert saving, "the run never reached the saving step"
    assert "calls" not in saving[0]


def test_every_step_says_how_long_it_took(db, owner, sample_images, settings, bus, scripted_graph):
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    published = _steps_of(db, owner, run)

    assert published
    assert all(isinstance(p["duration_ms"], int) and p["duration_ms"] >= 0 for p in published)


def test_the_sequence_continues_across_the_pause(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """One connection spans both halves, so the numbers it sees must not restart."""
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    before = [event.sequence for event in RunRepository(db).events(owner, run.id)]

    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)
    after = [event.sequence for event in RunRepository(db).events(owner, run.id)]

    assert after[: len(before)] == before
    assert after[len(before)] == before[-1] + 1


def test_no_event_names_a_node(db, owner, sample_images, settings, bus, scripted_graph):
    """A client rendering `identify_plant` is a client coupled to a function name."""
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    rendered = str([event.payload for event in RunRepository(db).events(owner, run.id)])
    for node in steps.STEPS:
        assert node not in rendered


def test_a_watcher_receives_the_events_as_they_happen(
    db, owner, sample_images, settings, bus, scripted_graph
):
    run, state = _run_and_state(db, owner, sample_images)
    watcher = bus.subscribe(run.id)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    received = []
    while (event := watcher.next(timeout=0.1)) is not None:
        received.append(event)
    assert [event.kind for event in received][-1] == steps.QUESTIONS


def test_a_failing_graph_produces_a_failed_run(db, owner, sample_images, settings, bus):
    def _explodes(**_):
        raise RuntimeError("the vision provider returned nonsense")

    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=_explodes, db=db)

    assert RunRepository(db).get(owner, run.id).status == run_status.FAILED


def test_a_failure_tells_the_client_nothing_about_what_broke(
    db, owner, sample_images, settings, bus
):
    """An exception message can carry a query, a filename, or a fragment of somebody's
    data. The same sentence goes out whatever happened."""

    def _explodes(**_):
        raise RuntimeError("psycopg: SELECT secrets FROM somewhere WHERE id = 42")

    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=_explodes, db=db)

    failed = RunRepository(db).get(owner, run.id)
    assert failed.error == worker.FAILURE
    assert "psycopg" not in failed.error
    assert "SELECT" not in failed.error


def test_a_failure_is_announced_on_the_stream(db, owner, sample_images, settings, bus):
    def _explodes(**_):
        raise RuntimeError("no")

    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=_explodes, db=db)

    events = RunRepository(db).events(owner, run.id)
    assert events[-1].kind == steps.FAILED


def test_a_completed_run_records_what_it_spent(
    db, owner, sample_images, settings, bus, scripted_graph
):
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    recorded = db.scalars(select(UsageEvent).where(UsageEvent.user_id == owner)).all()
    assert len(recorded) == 1
    assert recorded[0].succeeded is True


def test_a_paused_run_records_nothing_yet(db, owner, sample_images, settings, bus, scripted_graph):
    """Recording at the pause and again after the resume would count one run twice."""
    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    assert db.scalars(select(UsageEvent).where(UsageEvent.user_id == owner)).all() == []


def test_a_failed_run_records_what_it_spent_before_failing(db, owner, sample_images, settings, bus):
    """A quota that only sees successes is one somebody can exhaust by failing."""

    def _explodes(**_):
        raise RuntimeError("no")

    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=_explodes, db=db)

    recorded = db.scalars(select(UsageEvent).where(UsageEvent.user_id == owner)).all()
    assert len(recorded) == 1
    assert recorded[0].succeeded is False


def test_a_run_that_is_not_queued_is_left_alone(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """Cancelled between being queued and being picked up. The worker must not start it."""
    run, state = _run_and_state(db, owner, sample_images, status=run_status.CANCELLED)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    assert RunRepository(db).get(owner, run.id).status == run_status.CANCELLED
    assert RunRepository(db).events(owner, run.id) == []


def test_a_cancellation_stops_the_run_between_nodes(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """Cooperative, checked before each node. The step in flight finishes; no later one
    begins."""
    run, state = _run_and_state(db, owner, sample_images)
    RunRepository(db).request_cancel(owner, run.id)
    db.commit()

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    assert RunRepository(db).get(owner, run.id).status == run_status.CANCELLED


def test_the_clock_used_is_the_real_one(db, owner, sample_images, settings, bus, scripted_graph):
    """The worker stamps events itself rather than taking a clock, because it runs long
    after the request that started it. Asserted so the choice is visible."""
    run, state = _run_and_state(db, owner, sample_images)
    before = datetime.now(UTC)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    events = RunRepository(db).events(owner, run.id)
    assert events[0].occurred_at >= before


def test_a_paused_run_does_not_advance_further(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """The pause is the end of the pass. A worker that kept going would spend the second
    half of a diagnosis on answers nobody gave."""
    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    events = RunRepository(db).events(owner, run.id)
    assert events[-1].kind == steps.QUESTIONS
    assert RunRepository(db).get(owner, run.id).diagnosis_id is None


def test_the_pause_releases_the_worker_rather_than_holding_it(
    db, owner, sample_images, settings, bus, make_deps, make_pipeline_models
):
    """A pool of one, and a run waiting for a person.

    If the pause blocked inside the graph, the second run could not start until somebody
    read their email — and with a pool of one, nobody else could run anything at all. This
    is why `awaiting_answers` is a real status rather than a label on a stuck thread.
    """
    from runs.executor import ThreadPoolRunExecutor

    def _own_graph():
        """Each run gets its own models: the scripts are ordered and consumed."""
        gate, vision, chat = make_pipeline_models()
        graph = build_diagnosis_graph(
            make_deps(gate_model=gate, vision_model=vision, chat_model=chat), MemorySaver()
        )
        return lambda **_: graph

    first, first_state = _run_and_state(db, owner, sample_images)
    second, second_state = _run_and_state(db, owner, sample_images)
    pool = ThreadPoolRunExecutor(pool_size=1, queue_limit=4)
    finished = threading.Event()

    try:
        pool.submit(
            lambda: _execute(
                first, first_state, settings=settings, bus=bus, graph=_own_graph(), db=db
            )
        )
        pool.submit(
            lambda: (
                _execute(
                    second, second_state, settings=settings, bus=bus, graph=_own_graph(), db=db
                ),
                finished.set(),
            )
        )

        assert finished.wait(timeout=20.0), "the second run never started"
    finally:
        pool.shutdown()

    repo = RunRepository(db)
    assert repo.get(owner, first.id).status == run_status.AWAITING_ANSWERS
    assert repo.get(owner, second.id).status == run_status.AWAITING_ANSWERS


def test_one_watcher_sees_both_halves_of_a_run(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """The property the whole bus indirection exists for.

    A single subscription, held across the pause and the resume, receives the first half's
    steps, the questions, and then the second half's — with the sequence continuing rather
    than restarting. The graph's own generator ended in the middle of that; the watcher
    never noticed.
    """
    run, state = _run_and_state(db, owner, sample_images)
    watcher = bus.subscribe(run.id)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    received = []
    while (event := watcher.next(timeout=0.1)) is not None:
        received.append(event)

    kinds = [event.kind for event in received]
    assert steps.QUESTIONS in kinds
    assert kinds[-1] == steps.COMPLETED
    assert kinds.index(steps.QUESTIONS) < kinds.index(steps.COMPLETED)
    assert [event.sequence for event in received] == sorted(event.sequence for event in received)


def test_the_subscription_is_not_closed_by_the_pause(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """A pause that closed the stream would make every client handle a run as two."""
    run, state = _run_and_state(db, owner, sample_images)
    watcher = bus.subscribe(run.id)

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    assert watcher.closed is False


def test_the_step_in_flight_finishes_before_a_cancellation_takes_effect(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """Cooperative, not pre-emptive. Killing the thread mid-call would leak its connection
    and could leave a half-written checkpoint, which is a worse trade than a few cents.
    """
    run, state = _run_and_state(db, owner, sample_images)
    RunRepository(db).request_cancel(owner, run.id)
    db.commit()

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    events = RunRepository(db).events(owner, run.id)
    assert events, "the node already executing was abandoned rather than allowed to finish"
    assert events[-1].kind == steps.CANCELLED


def test_a_cancelled_run_records_what_it_spent(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """The money left when the model was called, not when somebody read the result."""
    run, state = _run_and_state(db, owner, sample_images)
    RunRepository(db).request_cancel(owner, run.id)
    db.commit()

    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)

    recorded = db.scalars(select(UsageEvent).where(UsageEvent.user_id == owner)).all()
    assert len(recorded) == 1
    assert recorded[0].succeeded is False


def test_a_rejected_photograph_says_why(db, owner, sample_images, settings, bus, make_deps):
    """A run can finish without a diagnosis: the intake guard refuses a photograph that is
    not a plant. Nothing broke, so it is not a failure — but `completed` with a null
    diagnosis and no reason tells somebody nothing, and it is the likeliest first thing
    anybody sees. Found by running the README's own commands against a live server.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from agent.schemas import PlantCheck
    from tests.fakes.chat_models import ScriptedStructuredModel

    gate = ScriptedStructuredModel([PlantCheck(is_plant=False, what_it_is="a doorknob")])
    graph = build_diagnosis_graph(make_deps(gate_model=gate), MemorySaver())
    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=lambda **_: graph, db=db)

    finished = RunRepository(db).get(owner, run.id)
    assert finished.status == run_status.COMPLETED
    assert finished.diagnosis_id is None
    assert finished.error, "a rejected run finished with no explanation"

    terminal = RunRepository(db).events(owner, run.id)[-1]
    assert terminal.kind == steps.COMPLETED
    assert terminal.payload["rejected"] is True
    assert terminal.payload["reason"]


def test_an_ordinary_completion_is_not_marked_rejected(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """The other side. A flag that were always true would pass the test above."""
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    terminal = RunRepository(db).events(owner, run.id)[-1]
    assert terminal.payload["rejected"] is False
    assert RunRepository(db).get(owner, run.id).error is None


def test_a_completed_run_names_the_plant_it_created(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """A run started without a plant makes one. Without this the client has a diagnosis and
    no way to reach the plant it belongs to — it would have to find it by guessing from a
    timestamp.
    """
    from data.models import Plant

    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    finished = RunRepository(db).get(owner, run.id)
    assert finished.plant_id is not None
    assert db.get(Plant, finished.plant_id).id == finished.plant_id


def test_the_terminal_event_names_the_plant_too(
    db, owner, sample_images, settings, bus, scripted_graph
):
    """A watcher that saw the run finish should not have to fetch it again to know where to
    go next."""
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=scripted_graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=scripted_graph, db=db, resume=ANSWERS)

    terminal = RunRepository(db).events(owner, run.id)[-1]
    assert terminal.payload["plant_id"]


# What a run is charged for -------------------------------------------------
#
# The tests above assert *whether* usage was recorded. None of them asserted how much,
# and that is exactly how an interrupted diagnosis came to be charged at half price: the
# scripted models report no usage at all, so `UsageCollector.snapshot()` is `None`
# throughout and every figure looks alike. These graphs report usage on purpose.


def _spent(prompt: int, completion: int, cost: float | None = None) -> LLMResult:
    usage = {"prompt_tokens": prompt, "completion_tokens": completion}
    if cost is not None:
        usage["cost"] = cost
    return LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="x"))]],
        llm_output={"token_usage": usage, "model_name": "test"},
    )


class _SpendingGraph:
    """Reports token usage through the run's collector, pauses once, then finishes.

    Deliberately not a real graph: what is under test is the worker's accounting across
    the pause, and a real graph cannot be made to report usage without a real model.
    """

    def __init__(self, *passes: LLMResult) -> None:
        self._passes = list(passes)
        self._done = 0
        # What each pass was handed. Recorded because the ledger being right is only half
        # of one run being accounted for: the node that writes the diagnosis record runs
        # inside the graph, and can only add the earlier pass's spend if the config says
        # what it was.
        self.configs: list[dict] = []

    def __call__(self, **_):
        return self

    def stream(self, payload, config, stream_mode=None):
        self.configs.append(config)
        config["configurable"]["usage_collector"].on_llm_end(self._passes[self._done])
        first = self._done == 0
        self._done += 1
        if first:
            # Pauses like the clarifying-question interrupt does.
            yield {"__interrupt__": [{"questions": [{"key": "watering", "prompt": "How often?"}]}]}

    def get_state(self, config):
        @dataclass
        class _State:
            values: dict

        return _State(values={})


def test_a_diagnosis_is_charged_for_both_of_its_passes(db, owner, sample_images, settings, bus):
    """The bug this guards: the pass that finishes only knows what it spent, and the
    expensive calls happen before the pause. Charging its snapshot alone charged roughly
    half of every diagnosis, against both the owner's quota and the daily spend cap."""
    graph = _SpendingGraph(_spent(1000, 200, cost=0.004), _spent(30, 10, cost=0.001))
    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=graph, db=db, resume=ANSWERS)

    recorded = db.scalars(select(UsageEvent).where(UsageEvent.user_id == owner)).all()
    assert len(recorded) == 1
    assert recorded[0].prompt_tokens == 1030
    assert recorded[0].completion_tokens == 210
    assert recorded[0].cost_usd == pytest.approx(0.005)


def test_the_resumed_pass_is_told_what_the_pause_carried(db, owner, sample_images, settings, bus):
    """The other half of charging a run once, for all of it.

    `cba92c0` fixed the ledger, which the worker writes after the graph returns. The
    *diagnosis record* is written by `agent/nodes/persist` inside the graph's own
    transaction — deliberately, so a crash cannot leave a diagnosis with a NULL cost
    (`M12`) — so the only way it can include the pre-interrupt spend is for the config to
    carry it. Until it did, `usage_events` held the whole run and `diagnoses.cost_usd`
    held the finishing pass, and the two disagreed on every interrupted diagnosis.
    """
    graph = _SpendingGraph(_spent(1000, 200, cost=0.004), _spent(30, 10, cost=0.001))
    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=graph, db=db)
    _execute(run, None, settings=settings, bus=bus, graph=graph, db=db, resume=ANSWERS)

    # Nothing had been spent when the first pass began, so there is nothing to carry.
    assert graph.configs[0]["configurable"].get("carried_usage") is None
    assert graph.configs[1]["configurable"].get("carried_usage") == UsageSnapshot(
        prompt_tokens=1000, completion_tokens=200, cost_usd=0.004
    )


def test_the_pause_carries_its_spend_on_the_run(db, owner, sample_images, settings, bus):
    """Not in the ledger — on the run. The pause has spent real money and has not
    finished, so the figure has to survive the worker thread without being charged yet."""
    graph = _SpendingGraph(_spent(1000, 200, cost=0.004), _spent(30, 10))
    run, state = _run_and_state(db, owner, sample_images)

    _execute(run, state, settings=settings, bus=bus, graph=graph, db=db)

    carried = RunRepository(db).partial_usage_of(run.id)
    assert carried == UsageSnapshot(prompt_tokens=1000, completion_tokens=200, cost_usd=0.004)


def test_a_run_abandoned_at_the_interrupt_is_still_charged_for_what_it_spent(
    db, owner, sample_images, settings, bus
):
    """Nobody answered, so the sweeper gave up on it. The vision and gate calls were still
    made and still cost money; recording a null cost made an abandoned diagnosis free."""
    graph = _SpendingGraph(_spent(1000, 200, cost=0.004))
    run, state = _run_and_state(db, owner, sample_images)
    _execute(run, state, settings=settings, bus=bus, graph=graph, db=db)

    sweeper.sweep(db, settings=settings, bus=bus, now=datetime.now(UTC) + timedelta(days=1))

    recorded = db.scalars(select(UsageEvent).where(UsageEvent.user_id == owner)).all()
    assert len(recorded) == 1
    assert recorded[0].prompt_tokens == 1000
    assert recorded[0].cost_usd == pytest.approx(0.004)
    assert recorded[0].succeeded is False
