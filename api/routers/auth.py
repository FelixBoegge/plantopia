"""Registering, and proving an address.

Every endpoint here is unauthenticated by definition, which makes them the ones a stranger
can reach. Two properties follow, and both are load-bearing:

- **The answer never depends on whether an address is registered.** Same status, same body.
- **Nothing is echoed.** A response carries no password, no hash, and no token.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from api import cookies
from api.dependencies import MailerDep, SessionDep, SettingsDep
from api.schemas import LoginIn, RegisterIn, SessionOut, VerifyIn
from identity import accounts, sessions

RefreshCookie = Annotated[str | None, Cookie(alias=cookies.NAME)]

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


@router.post("/login", response_model=SessionOut)
def login(
    body: LoginIn, response: Response, session: SessionDep, settings: SettingsDep
) -> SessionOut:
    """Sign in.

    The access token comes back in the body, where the client holds it in memory and sends
    it as a bearer header. The refresh token does not: it goes out as an httpOnly cookie,
    so a script that manages to run on the page cannot read the long-lived half.
    """
    user = accounts.authenticate(session, email=body.email, password=body.password)
    issued = sessions.start(session, user_id=user.id, settings=settings)

    cookies.attach(response, issued.refresh_token, settings=settings)
    return SessionOut(
        access_token=issued.access_token,
        expires_in_seconds=settings.access_token_minutes * 60,
    )


@router.post("/refresh", response_model=SessionOut)
def refresh(
    response: Response, session: SessionDep, settings: SettingsDep, presented: RefreshCookie = None
) -> SessionOut:
    """Exchange the refresh cookie for a new pair.

    Not retried by the client. A refresh whose response is lost has still rotated, so
    presenting the same token again looks exactly like a stolen one being used — and is
    treated as one.
    """
    if not presented:
        raise sessions.InvalidRefreshTokenError("no refresh token was presented")

    issued = sessions.refresh(session, presented=presented, settings=settings)

    cookies.attach(response, issued.refresh_token, settings=settings)
    return SessionOut(
        access_token=issued.access_token,
        expires_in_seconds=settings.access_token_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response, session: SessionDep, settings: SettingsDep, presented: RefreshCookie = None
) -> None:
    """Sign out.

    Ends the whole family, not just the presented token, and clears the cookie. An access
    token already issued is left to expire on its own — it cannot be revoked, and pretending
    otherwise would be a worse lie than the fifteen minutes it has left.

    Answers 204 whether or not the token was recognised. Signing out is a request to be
    signed out, and reporting that a token was already invalid tells an unauthenticated
    caller which tokens exist.
    """
    if presented:
        sessions.end(session, presented=presented)
    cookies.clear(response, settings=settings)
