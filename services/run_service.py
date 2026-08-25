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
from uuid import UUID

from agent.schemas import ImageRef
from agent.state import DiagnosisState
from agent.threads import diagnosis_thread
from core.config import Settings
from data.engine import transaction
from data.repositories import runs as run_status
from data.repositories.errors import RecordNotFoundError
from data.repositories.plants import PlantRepository
from data.repositories.runs import EventRecord, RunRecord, RunRepository
from data.repositories.usage import UsageRepository
from runs.bus import EventBus
from runs.executor import RunExecutor
from runs.worker import execute
from services import limits

logger = logging.getLogger(__name__)


class RunConflictError(Exception):
    """The run is not in a state where this makes sense.

    Answering one that was never asked a question, cancelling one that has finished. A
    conflict rather than a refusal: nothing is wrong with the request except its timing.
    """


@dataclass(frozen=True, slots=True)
class StartRequest:
    """What starting a diagnosis needs."""

    images: list[ImageRef]
    plant_name: str
    location_kind: str
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
        # Passed through to the worker, which defaults it. Here so a test can drive a real
        # run against scripted models without patching a module.
        self._build_graph = build_graph

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

        state = DiagnosisState(
            images=request.images,
            plant_name=request.plant_name,
            location_kind=request.location_kind,
            location_text=request.location_text,
            user_notes=request.user_notes,
            plant_id=request.plant_id,
        )

        self._submit(run_id=run_id, thread_id=thread_id, initial_state=state, resume=None)
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

    def answer(self, run_id: UUID, answers: dict[str, str]) -> RunRecord:
        """Resume a paused run with the answers it asked for.

        The status check and the transition are one conditional update, so two submissions
        arriving together produce one resume and one conflict rather than two resumes of
        one thread — which would run the expensive half twice against one checkpoint.
        """
        run = self.get(run_id)
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

        self._submit(run_id=run_id, thread_id=thread_id, initial_state=None, resume=answers)
        return self.get(run_id)

    def cancel(self, run_id: UUID) -> None:
        """Ask a run to stop.

        Two steps rather than one, because a single boolean cannot say which of the two
        refusals happened: the run belonging to somebody else is 404, and the run having
        already finished is 409.
        """
        run = self.get(run_id)
        if not self._runs.request_cancel(self._user_id, run_id):
            raise RunConflictError(f"this run is already {run.status}")
        self._runs.session.commit()

    def _submit(self, *, run_id: UUID, thread_id: str, initial_state, resume) -> None:
        """Hand a pass to the executor.

        The run row is already committed, so a queue refusal leaves a ``queued`` run that
        the sweeper will fail rather than an orphan. That is the honest outcome: it *was*
        queued, and then there was no room.
        """
        user_id, settings, bus = self._user_id, self._settings, self._bus
        build_graph = self._build_graph

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
            )

        self._executor.submit(_work)

    def _require_plant(self, plant_id: UUID) -> None:
        """404 for another owner's plant, before anything else happens."""
        if self._plants.get(self._user_id, plant_id) is None:
            raise RecordNotFoundError(f"no plant {plant_id}")
