"""Registering, and proving an address.

Every endpoint here is unauthenticated by definition, which makes them the ones a stranger
can reach. Two properties follow, and both are load-bearing:

- **The answer never depends on whether an address is registered.** Same status, same body.
- **Nothing is echoed.** A response carries no password, no hash, and no token.
"""

from fastapi import APIRouter, status

from api.dependencies import MailerDep, SessionDep, SettingsDep
from api.schemas import RegisterIn, VerifyIn
from identity import accounts

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
def register(
    body: RegisterIn, session: SessionDep, settings: SettingsDep, mailer: MailerDep
) -> dict:
    """Create an unverified account and send the address a way to prove itself.

    202 rather than 201: whether anything was created is exactly what this response must
    not reveal. "Accepted, check your email" is true for both outcomes, and is also the
    only instruction the caller needs.
    """
    accounts.register(
        session,
        email=body.email,
        password=body.password,
        consented=body.accepted_privacy_notice,
        settings=settings,
        mailer=mailer,
    )
    return {"detail": "If that address can be registered, a confirmation message is on its way."}


@router.post("/verify", status_code=status.HTTP_204_NO_CONTENT)
def verify(body: VerifyIn, session: SessionDep) -> None:
    """Prove an address by spending the link that was mailed to it."""
    accounts.verify(session, presented=body.token)
