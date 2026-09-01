"""Who is signed in, what the harness last measured, and how to stop being here.

Everything on this router answers a question about the person asking rather than about
something they own, which is why none of it takes an identifier: an endpoint that accepted
one would be an endpoint that could be pointed at somebody else, defended only by a check
somebody has to remember to write.
"""

from dataclasses import asdict

from fastapi import APIRouter, Response, status

from agent.wiring import now_utc
from api.dependencies import (
    BlobStoreDep,
    EvaluationAccessDep,
    OwnerDep,
    SessionDep,
    SettingsDep,
)
from api.schemas import AccountOut, DeleteAccountIn, EvaluationOut
from services import account, erasure, evaluations, export

router = APIRouter(tags=["account"])


@router.get("/me", response_model=AccountOut)
def me(session: SessionDep, owner: OwnerDep, settings: SettingsDep) -> AccountOut:
    """The signed-in person's own account.

    One request rather than three, because a screen needs the identity, the consent record
    and the allowance together — and a client assembling them from three responses is a
    client rendering a page that is briefly wrong.
    """
    described = account.describe(session, user_id=owner, settings=settings, now=now_utc())
    # ``asdict`` rather than ``vars``: the record uses ``slots``, so it has no ``__dict__``.
    return AccountOut(**asdict(described))


@router.get("/evaluation/latest", response_model=EvaluationOut)
def latest_evaluation(owner: EvaluationAccessDep, settings: SettingsDep) -> EvaluationOut:
    """What the evaluation harness last produced.

    Refused to anybody whose account does not permit it, with a 404 rather than a 403 —
    a refusal that distinguishes the two tells a stranger the route exists.
    """
    result = evaluations.latest(settings.eval_results_path)
    return EvaluationOut(generated_at=result.generated_at, results=result.results)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    body: DeleteAccountIn, session: SessionDep, owner: OwnerDep, settings: SettingsDep
) -> Response:
    """Erase the signed-in account and everything belonging to it.

    Takes no identifier, deliberately: the only account this can delete is the one the
    request is already authenticated as.

    The service owns the transaction, and opens it only after the confirmation passes —
    a refusal must not roll back anything. The conversation checkpoints are swept first on
    their own connection; `services/erasure.delete_account` says why that order is the
    survivable one.
    """
    erasure.confirm_and_delete(
        session,
        user_id=owner,
        password=body.password,
        confirmation=body.confirmation,
        settings=settings,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/export")
def export_me(
    session: SessionDep, owner: OwnerDep, blobs: BlobStoreDep, settings: SettingsDep
) -> Response:
    """Everything held about the signed-in person, as one archive.

    Takes no identifier, for the same reason `delete_me` does not.

    A buffered response rather than a stream: the archive is assembled in memory behind a
    size guard, and streaming it would mean holding a database session open for the whole
    download to save memory the deployment is not short of.
    """
    built = export.build(session, user_id=owner, blobs=blobs, settings=settings, now=now_utc())
    return Response(
        content=built.content,
        media_type="application/zip",
        # So a browser saves it with a name rather than the endpoint's path.
        headers={"Content-Disposition": f'attachment; filename="{built.filename}"'},
    )
