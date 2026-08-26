"""Starting a diagnosis, and following it.

Every endpoint here answers immediately. The work takes about ninety seconds and pauses
part-way to ask questions, and neither of those fits inside a request — so what a client
gets back is a run to watch, never a result to wait for.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Request, UploadFile, status

from api import converters, streaming
from api.dependencies import BlobStoreDep, RunServiceDep, SessionDep, SettingsDep
from api.schemas import AnswersIn, RunOut
from core.images import store_upload
from runs.bus import bus
from services.run_service import StartRequest

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def start_run(
    service: RunServiceDep,
    blobs: BlobStoreDep,
    settings: SettingsDep,
    plant_name: Annotated[str, Form()],
    location_kind: Annotated[str, Form()],
    photographs: Annotated[list[UploadFile], File()],
    location_text: Annotated[str | None, Form()] = None,
    user_notes: Annotated[str | None, Form()] = None,
    stated_species: Annotated[str | None, Form()] = None,
    plant_id: Annotated[UUID | None, Form()] = None,
) -> RunOut:
    """Begin a diagnosis.

    202, not 201: the run exists, and the thing the client actually wants does not yet.
    The response carries no diagnosis and no result — only what to watch.

    Photographs are stored before the run is created, so a rejected upload is refused
    without leaving a run behind. `M8` records that a batch failing part-way leaves the
    earlier images stored; that is unchanged here and still storage litter rather than
    anything a client can see.
    """
    images = [
        store_upload(
            photograph.file.read(), blobs=blobs, user_id=service.user_id, settings=settings
        )
        for photograph in photographs
    ]

    run = service.start(
        StartRequest(
            images=images,
            plant_name=plant_name,
            location_kind=location_kind,
            location_text=location_text,
            user_notes=user_notes,
            # Blank is absent. A form sends an empty string for a field somebody left
            # alone, and an empty string carried as a species would lead the candidates
            # with nothing.
            stated_species=(stated_species or "").strip() or None,
            plant_id=plant_id,
        )
    )
    return converters.run(run)


@router.get("", response_model=list[RunOut])
def list_runs(service: RunServiceDep) -> list[RunOut]:
    """This owner's runs, most recent first."""
    return [converters.run(run) for run in service.list_runs()]


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: UUID, service: RunServiceDep) -> RunOut:
    """One run.

    A client polls this when it cannot hold a stream open, and reads it after a stream
    closes to find out how the run ended. Either way it reads a status rather than
    inferring one.
    """
    return converters.run(service.get(run_id))


@router.post("/{run_id}/answers", response_model=RunOut)
def answer_run(run_id: UUID, body: AnswersIn, service: RunServiceDep) -> RunOut:
    """Answer the questions a paused run asked, and let it continue."""
    return converters.run(service.answer(run_id, body.answers))


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_run(run_id: UUID, service: RunServiceDep) -> None:
    """Abandon a run.

    The step already in flight finishes; no later one begins. Cancelling during a slow
    model call still pays for that call — killing the thread would leak its connection and
    could leave a half-written checkpoint, which is a worse trade than a few cents.
    """
    service.cancel(run_id)


@router.get("/{run_id}/events")
async def stream_events(
    run_id: UUID,
    request: Request,
    service: RunServiceDep,
    session: SessionDep,
    settings: SettingsDep,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
):
    """Follow a run as it works.

    Replays what has already happened, then follows live on the same connection — including
    across the pause for clarifying questions, which is a gap between two publishes rather
    than the end of anything.

    A client reconnecting sends `Last-Event-ID` and receives only what it missed. That is
    what makes a reload or a dropped tunnel cost nothing: the owner has already paid for
    this run and waited for it.
    """
    after = streaming.last_seen(last_event_id)
    service.get(run_id)  # 404 for a stranger before a single event is read

    def _replay(since: int):
        return service.events(run_id, after=since)

    response = await streaming.stream_run(
        request=request,
        run_id=run_id,
        bus=bus,
        replay=_replay,
        after=after,
        keepalive_seconds=settings.run_keepalive_seconds,
    )

    # Hand the connection back before streaming. A stream lives for minutes, and the
    # dependency that opened this session will not close it until the response completes —
    # which would tie up a pooled connection for every watcher, on top of one per run.
    session.close()
    return response
