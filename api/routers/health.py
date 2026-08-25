"""Liveness and readiness.

Deliberately two endpoints. Alive is not the same as able to serve, and an orchestrator
that cannot tell them apart restarts a container which is merely waiting for its database
— turning a slow start into a crash loop.
"""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from api.dependencies import SessionDep
from api.schemas import HealthOut, ReadyOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    """The process is running. Touches nothing else, on purpose."""
    return HealthOut(status="ok")


@router.get("/ready", response_model=ReadyOut)
def ready(session: SessionDep, response: Response) -> ReadyOut:
    """The process can serve requests, which means it can reach its database.

    Reports 503 rather than raising, so a probe reads a status code rather than a stack
    trace, and the body says which dependency was the problem.
    """
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — any failure to reach the database means not ready
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyOut(status="not ready", database=False)
    return ReadyOut(status="ready", database=True)
