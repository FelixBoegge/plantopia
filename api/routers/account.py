"""Who is signed in, and what the harness last measured.

Two endpoints that have nothing in common except that both answer a question about the
person asking rather than about something they own.
"""

from dataclasses import asdict

from fastapi import APIRouter

from agent.wiring import now_utc
from api.dependencies import EvaluationAccessDep, OwnerDep, SessionDep, SettingsDep
from api.schemas import AccountOut, EvaluationOut
from services import account, evaluations

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
