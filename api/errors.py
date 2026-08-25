"""One shape for every failure.

RFC 9457 problem details: a machine-readable ``type`` a client can branch on, a human
title, the status, and nothing else. Clients are expected to switch on ``type``, which
makes it part of the interface rather than an implementation detail — changing one for a
given failure is a change to the specification.

Registered on the application rather than caught per handler. Twenty handlers would mean
twenty chances for one to return a bare string or let a database message through; a
handler that simply lets ``RecordNotFoundError`` escape is doing the right thing.
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.dependencies import NotSignedInError, SessionExpiredError
from data.repositories.errors import RecordNotFoundError
from identity.accounts import AuthenticationError, RegistrationError, VerificationError
from identity.sessions import SessionError

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/problem+json"

# Stable identifiers. A client branches on these, so they are as much a contract as the
# status codes beside them.
TYPE_NOT_FOUND = "https://plantopia.example/problems/not-found"
TYPE_INVALID_REQUEST = "https://plantopia.example/problems/invalid-request"
TYPE_INTERNAL = "https://plantopia.example/problems/internal-error"
TYPE_INVALID_LINK = "https://plantopia.example/problems/invalid-link"
TYPE_UNAUTHENTICATED = "https://plantopia.example/problems/unauthenticated"
TYPE_SESSION_EXPIRED = "https://plantopia.example/problems/session-expired"


def problem(
    *, status_code: int, type_: str, title: str, detail: str | None = None, **extra
) -> JSONResponse:
    """Build a problem-details response."""
    body: dict = {"type": type_, "title": title, "status": status_code}
    if detail is not None:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(status_code=status_code, content=body, media_type=CONTENT_TYPE)


def register(app: FastAPI) -> None:
    """Install the handlers that turn exceptions into problem details."""

    @app.exception_handler(RecordNotFoundError)
    def _not_found(request: Request, exc: RecordNotFoundError) -> JSONResponse:
        """404, never 403.

        The repositories already refuse another owner's record; this is the half that
        stops the status code undoing that refusal. A 403 asserts the thing exists and is
        being withheld, which tells a stranger it exists.
        """
        return problem(
            status_code=status.HTTP_404_NOT_FOUND,
            type_=TYPE_NOT_FOUND,
            title="Not found",
            detail="No such resource.",
        )

    @app.exception_handler(NotSignedInError)
    def _not_signed_in(request: Request, exc: NotSignedInError) -> JSONResponse:
        """No usable access token. The client signs in."""
        return problem(
            status_code=status.HTTP_401_UNAUTHORIZED,
            type_=TYPE_UNAUTHENTICATED,
            title="Not signed in",
            detail="This endpoint needs a signed-in account.",
        )

    @app.exception_handler(SessionExpiredError)
    def _expired(request: Request, exc: SessionExpiredError) -> JSONResponse:
        """A token that was ours and has run out. The client refreshes.

        Distinct from ``NotSignedInError`` so the client knows which of the two to do. One
        that cannot tell them apart either signs people out every fifteen minutes or retries
        a sign-in that will never work.
        """
        return problem(
            status_code=status.HTTP_401_UNAUTHORIZED,
            type_=TYPE_SESSION_EXPIRED,
            title="Session expired",
            detail="The access token has expired. Refresh it and try again.",
        )

    @app.exception_handler(AuthenticationError)
    def _refused_sign_in(request: Request, exc: AuthenticationError) -> JSONResponse:
        """One answer for every reason a sign-in fails.

        Unknown address, wrong password and unverified account are indistinguishable here.
        Separating them would turn sign-in into a way to ask who has an account, and the
        third would additionally say whether that person has read their email.
        """
        return problem(
            status_code=status.HTTP_401_UNAUTHORIZED,
            type_=TYPE_UNAUTHENTICATED,
            title="Not signed in",
            detail="Those credentials were not accepted.",
        )

    @app.exception_handler(SessionError)
    def _refused_refresh(request: Request, exc: SessionError) -> JSONResponse:
        """A refresh that cannot be honoured, including a reused token whose family has
        just been invalidated.

        Both mean the same thing to the client — sign in again — so both get the same
        answer. Which one it was is in the log, where it is somebody's job to look.
        """
        return problem(
            status_code=status.HTTP_401_UNAUTHORIZED,
            type_=TYPE_UNAUTHENTICATED,
            title="Not signed in",
            detail="This session has ended. Sign in again.",
        )

    @app.exception_handler(RegistrationError)
    def _registration(request: Request, exc: RegistrationError) -> JSONResponse:
        """A registration the caller can fix: a password below the minimum, or a privacy
        notice not agreed to.

        The detail is safe to return because neither refusal depends on whether the address
        is registered — they are decided before anything is looked up.
        """
        return problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            type_=TYPE_INVALID_REQUEST,
            title="Invalid request",
            detail=str(exc),
        )

    @app.exception_handler(VerificationError)
    def _bad_link(request: Request, exc: VerificationError) -> JSONResponse:
        """A verification link that cannot be honoured.

        One answer for unknown, expired and already-spent, and one detail that does not say
        which. A stranger holding a link should not learn from the refusal whether it was
        ever real.
        """
        return problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            type_=TYPE_INVALID_LINK,
            title="This link cannot be used",
            detail="The link is invalid, has expired, or has already been used. Request a new one.",
        )

    @app.exception_handler(ValueError)
    def _invalid(request: Request, exc: ValueError) -> JSONResponse:
        """A service refusing its input — a blank plant name, an unknown step status.

        ``RecordNotFoundError`` subclasses ``ValueError`` and is registered above; FastAPI
        dispatches on the most specific handler, so the two do not collide.
        """
        return problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            type_=TYPE_INVALID_REQUEST,
            title="Invalid request",
            detail=str(exc),
        )

    @app.exception_handler(RequestValidationError)
    def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        """A malformed body or path parameter, named field by field.

        Errors are reduced to location and message. FastAPI's raw errors can carry the
        offending input, which for this application could be somebody's chat message.
        """
        return problem(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            type_=TYPE_INVALID_REQUEST,
            title="Invalid request",
            detail="The request could not be understood.",
            errors=[
                {"location": list(error.get("loc", ())), "message": error.get("msg", "")}
                for error in exc.errors()
            ],
        )

    @app.exception_handler(Exception)
    def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Anything unforeseen.

        The cause goes to the log and not to the client: an exception message here could
        carry a query, a connection string, or a fragment of somebody's data.

        ``exc_info=exc`` rather than ``logger.exception``. A Starlette handler is called
        with the exception as an argument and *not* from inside an ``except`` block, so
        there is no active exception for the logger to find — it recorded "NoneType:
        None" and the traceback was lost, which is the whole thing this log exists for.
        """
        logger.error(
            "unhandled error serving %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            type_=TYPE_INTERNAL,
            title="Internal error",
            detail="Something went wrong. The details have been logged.",
        )


ExceptionHandler = Callable[[Request, Exception], Awaitable[JSONResponse] | JSONResponse]
