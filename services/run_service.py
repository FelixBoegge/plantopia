"""Starting, reading, answering and abandoning runs.

The request half. Everything here happens inside a request and must be quick: it validates,
it writes a row, it hands work to the executor, and it returns. What the work then does is
``runs/worker.py``'s business.

**The ceilings apply before the row exists.** A run refused for cost must leave nothing
behind — not a record, not a count against the allowance that refused it — or the second
attempt is refused by the first attempt's failure.

**Ownership is established once, here.** The worker carries a run id and no person, which
is why the repository's worker-side methods take no owner: adding one would mean threading
a value through the pool solely to satisfy a signature.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from agent.schemas import ImageRef, Question
from agent.state import DiagnosisState
from agent.threads import diagnosis_thread
from core.config import Settings
from data.engine import transaction
from data.repositories import runs as run_status
from data.repositories.errors import RecordNotFoundError
from data.repositories.plants import PlantRepository
from data.repositories.runs import EventRecord, RunRecord, RunRepository
from data.repositories.usage import UsageRepository
from runs import steps
from runs.bus import Event, EventBus
from runs.executor import RunExecutor
from runs.worker import execute
from services import limits

logger = logging.getLogger(__name__)


class MissingAnswerError(Exception):
    """A required question was left empty.

    Distinct from a conflict: the run is exactly where it should be and the request is
    fixable by the person who made it, which is the definition of a 400 rather than a 409.
    """

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        super().__init__(
            "these questions have to be answered before the diagnosis can go on: " + ", ".join(keys)
        )


class RunConflictError(Exception):
    """The run is not in a state where this makes sense.

    Answering one that was never asked a question, cancelling one that has finished. A
    conflict rather than a refusal: nothing is wrong with the request except its timing.
    """


@dataclass(frozen=True, slots=True)
class StartRequest:
    """What starting a diagnosis needs."""

    images: list[ImageRef]
    location_kind: str
    plant_name: str | None = None
    stated_species: str | None = None

    # What the photographs said about themselves. Read on the way in, because the bytes
    # that carried it are re-saved before they are stored.
    captured_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_text: str | None = None
    user_notes: str | None = None
    plant_id: UUID | None = None


class RunService:
    """One owner's runs."""

    def __init__(
        self,
        *,
        user_id: UUID,
        tier: str,
        runs: RunRepository,
        plants: PlantRepository,
        usage: UsageRepository,
        executor: RunExecutor,
        bus: EventBus,
        settings: Settings,
        now,
        build_graph=None,
        session_factory=None,
    ) -> None:
        self._user_id = user_id
        self._tier = tier
        self._runs = runs
        self._plants = plants
        self._usage = usage
        self._executor = executor
        self._bus = bus
        self._settings = settings
        self._now = now
        # Passed through to the worker, which defaults both. Here so that a test can drive
        # a real run end to end — service, worker and back — without patching a module. The
        # seam earns its keep: the two halves once disagreed about what status a resumed run
        # is in, and only a test crossing this boundary could see it.
        self._build_graph = build_graph
        self._session_factory = session_factory

    def state_for(self, request: StartRequest) -> DiagnosisState:
        """The state a run starts from, including what its plant already knows.

        **A run that names a plant inherits that plant's location.** Nothing else supplies
        one: a re-check skips the questions pause, because roadmap-step completion answers
        what it would otherwise ask, and the upload form has no location field. So an
        outdoor plant with a town on its record produced a run that believed it had none,
        and the weather lookup — which needs one — returned nothing. The symptom was a first
        diagnosis with a weather graph and every re-check after it without one.

        What the request carries wins. A photograph that says where it was taken is about
        this photograph; the plant's record is about where it usually lives, and the
        specific one should not lose to the general.

        Only the location. The species and whether it lives indoors are already sent by the
        form, which reads them off the same record.
        """
        location_text = request.location_text
        if location_text is None and request.plant_id is not None:
            known = self._plants.get(self._user_id, request.plant_id)
            location_text = known.location_text if known else None

        return DiagnosisState(
            images=request.images,
            plant_name=request.plant_name,
            stated_species=request.stated_species,
            captured_at=request.captured_at,
            latitude=request.latitude,
            longitude=request.longitude,
            location_kind=request.location_kind,
            location_text=location_text,
            user_notes=request.user_notes,
            plant_id=request.plant_id,
        )

    @property
    def user_id(self) -> UUID:
        """Whose runs these are. Read by the upload handler, which stores photographs
        against the owner before there is a run to attach them to."""
        return self._user_id

    def start(self, request: StartRequest) -> RunRecord:
        """Begin a diagnosis and return immediately.

        Order matters and is deliberate: ownership, then the ceilings, then the row, then
        the submission. Each step is the cheapest one that can still refuse.
        """
        if request.plant_id is not None:
            self._require_plant(request.plant_id)

        limits.check(
            self._usage,
            user_id=self._user_id,
            tier=self._tier,
            settings=self._settings,
            now=self._now(),
        )

        thread_id = diagnosis_thread(self._user_id)
        with transaction(self._runs.session):
            run_id = self._runs.create(
                self._user_id,
                plant_id=request.plant_id,
                kind="diagnosis",
                thread_id=thread_id,
                now=self._now(),
            )

        self._submit(
            run_id=run_id,
            thread_id=thread_id,
            initial_state=self.state_for(request),
            resume=None,
        )
        return self._runs.get(self._user_id, run_id)

    def get(self, run_id: UUID) -> RunRecord:
        run = self._runs.get(self._user_id, run_id)
        if run is None:
            raise RecordNotFoundError(f"no run {run_id}")
        return run

    def list_runs(self, *, limit: int = 50) -> list[RunRecord]:
        """This owner's runs, most recent first.

        Not called ``list``: inside a class body that name shadows the builtin for every
        annotation below it, which fails at import rather than at the call site.
        """
        return self._runs.list_for_user(self._user_id, limit=limit)

    def events(self, run_id: UUID, *, after: int = 0) -> list[EventRecord]:
        self.get(run_id)  # 404 for a stranger before any event is read
        return self._runs.events(self._user_id, run_id, after=after)

    def activity(self, diagnosis_id: UUID) -> list[EventRecord]:
        """What the run that produced this diagnosis did, for a screen showing the result.

        Empty is a real answer, not a missing one: a diagnosis made before steps carried
        anything worth showing, or one whose run has since been swept, has no activity and
        the screen shows nothing rather than an empty heading.
        """
        return self._runs.steps_for_diagnosis(self._user_id, diagnosis_id)

    def answer(
        self,
        run_id: UUID,
        answers: dict[str, str],
        *,
        species: dict | None = None,
    ) -> RunRecord:
        """Resume a paused run with the answers it asked for, and any species chosen.

        The status check and the transition are one conditional update, so two submissions
        arriving together produce one resume and one conflict rather than two resumes of
        one thread — which would run the expensive half twice against one checkpoint.
        """
        run = self.get(run_id)
        self._require_answers(run_id, answers)
        if self._runs.cancel_requested(run_id):
            # Asked to stop, and then answered. Honouring the answer would restart work
            # somebody has already said they do not want.
            raise RunConflictError("this run has been cancelled")
        thread_id = self._runs.thread_of(self._user_id, run_id)

        with transaction(self._runs.session):
            claimed = self._runs.advance(
                run_id,
                expected=run_status.AWAITING_ANSWERS,
                to=run_status.QUEUED,
                now=self._now(),
            )
        if not claimed:
            raise RunConflictError(
                f"this run is {run.status}, so there is nothing waiting to be answered"
            )

        # Always the mapping shape, even with no species: one shape reaching the graph
        # means `gather_context` has one path to be right about, and the shape that reads a
        # bare answers dict exists only for a run paused before this deployment.
        self._submit(
            run_id=run_id,
            thread_id=thread_id,
            initial_state=None,
            resume={"answers": answers, "species": species},
        )
        return self.get(run_id)

    def _require_answers(self, run_id: UUID, answers: dict[str, str]) -> None:
        """Refuse a resume that leaves a required question empty.

        **Checked here as well as in the form.** A form is a convenience: it stops somebody
        submitting by accident, and it stops nothing else. This is the only place that can
        say no to a client that did not run one, and a run resumed without an outdoor
        plant's location is a diagnosis missing the half that weather explains.

        Checked *before* the run is claimed, so a refused submission leaves it paused and
        answerable rather than queued with nothing coming to pick it up.
        """
        missing = [
            question.key
            for question in self._questions_of(run_id)
            if question.required and not (answers.get(question.key) or "").strip()
        ]
        if missing:
            raise MissingAnswerError(missing)

    def _questions_of(self, run_id: UUID) -> list[Question]:
        """What the run asked, read back from the event it published when it paused.

        The graph's own state would answer this too, and reading it means opening a
        checkpoint connection for a validation. The event is already stored, already this
        owner's, and says exactly what the client was shown.
        """
        for event in self._runs.events(self._user_id, run_id):
            if event.kind != steps.QUESTIONS:
                continue
            asked = event.payload.get("questions") or []
            return [Question.model_validate(question) for question in asked]
        return []

    def cancel(self, run_id: UUID) -> None:
        """Stop a run.

        What that means depends on whether anything is executing.

        A ``running`` run has a worker inside the graph, so it gets the cooperative flag and
        stops between nodes — the step in flight finishes, because killing a thread mid-call
        leaks its connection and can leave a half-written checkpoint.

        A ``queued`` or ``awaiting_answers`` run has no worker at all. Setting a flag
        nothing reads would leave it exactly where it was: a paused run would sit there
        until the sweeper gave up on it an hour later, having been told to stop. So it ends
        here and now, and the conditional transition is what stops a worker that was about
        to pick it up from resurrecting it.

        Two steps rather than one, because a single boolean cannot say which refusal
        happened: somebody else's run is 404, an already-finished one is 409.
        """
        run = self.get(run_id)

        if run.status == run_status.RUNNING:
            if not self._runs.request_cancel(self._user_id, run_id):
                raise RunConflictError(f"this run is already {run.status}")
            self._runs.session.commit()
            return

        with transaction(self._runs.session):
            stopped = self._runs.advance(
                run_id,
                expected=frozenset({run_status.QUEUED, run_status.AWAITING_ANSWERS}),
                to=run_status.CANCELLED,
                now=self._now(),
            )
        if not stopped:
            raise RunConflictError(f"this run is already {run.status}")
        self._announce_cancelled(run_id)

    def _announce_cancelled(self, run_id: UUID) -> None:
        """Tell whoever is watching that a run they were following has stopped.

        The worker does this for a run it was executing. A run cancelled while queued or
        paused has no worker to do it, and a watcher would otherwise hold a connection open
        on something that has already ended.
        """
        payload: dict = {}
        with transaction(self._runs.session):
            sequence = self._runs.append_event(
                run_id, kind=steps.CANCELLED, payload=payload, now=self._now()
            )
        self._bus.publish(
            Event(run_id=run_id, sequence=sequence, kind=steps.CANCELLED, payload=payload)
        )
        self._bus.close_run(run_id)

    def _submit(self, *, run_id: UUID, thread_id: str, initial_state, resume) -> None:
        """Hand a pass to the executor.

        The run row is already committed, so a queue refusal leaves a ``queued`` run that
        the sweeper will fail rather than an orphan. That is the honest outcome: it *was*
        queued, and then there was no room.
        """
        user_id, settings, bus = self._user_id, self._settings, self._bus
        build_graph, session_factory = self._build_graph, self._session_factory

        def _work() -> None:
            execute(
                run_id=run_id,
                user_id=user_id,
                thread_id=thread_id,
                initial_state=initial_state,
                settings=settings,
                bus=bus,
                resume=resume,
                build_graph=build_graph,
                session_factory=session_factory,
            )

        self._executor.submit(_work)

    def _require_plant(self, plant_id: UUID) -> None:
        """404 for another owner's plant, before anything else happens."""
        if self._plants.get(self._user_id, plant_id) is None:
            raise RecordNotFoundError(f"no plant {plant_id}")
