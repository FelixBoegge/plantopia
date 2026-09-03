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
from api.rate_limit import RateLimitedError
from core.guards import UploadRejected
from data.repositories.errors import RecordNotFoundError
from identity.accounts import (
    AuthenticationError,
    PasswordChangeError,
    RegistrationError,
    ResetError,
    VerificationError,
)
from identity.sessions import SessionError
from runs.executor import QueueFullError
from services.erasure import ConfirmationError
from services.export import ExportTooLargeError
from services.limits import DailyCapReachedError, QuotaExceededError
from services.run_service import MissingAnswerError, RunConflictError

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
TYPE_QUOTA_EXCEEDED = "https://plantopia.example/problems/quota-exceeded"
TYPE_DAILY_CAP = "https://plantopia.example/problems/daily-cap-reached"
TYPE_MISSING_ANSWER = "https://plantopia.example/problems/missing-answer"
TYPE_RATE_LIMITED = "https://plantopia.example/problems/rate-limited"
TYPE_CONFLICT = "https://plantopia.example/problems/conflict"
TYPE_BUSY = "https://plantopia.example/problems/too-busy"


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

    @app.exception_handler(UploadRejected)
    def _bad_upload(request: Request, exc: UploadRejected) -> JSONResponse:
        """A photograph that is not one, or is too large.

        The reason is safe to return: it is written by ``core/guards.py`` for a person to
        read, and says nothing about the request beyond what the person just sent.
        """
        return problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            type_=TYPE_INVALID_REQUEST,
            title="That photograph could not be used",
            detail=exc.reason,
        )

    @app.exception_handler(MissingAnswerError)
    def _missing_answer(request: Request, exc: MissingAnswerError) -> JSONResponse:
        """A required question was left empty.

        400 rather than 409: the run is exactly where it should be, and the request is
        fixable by the person who made it. The keys travel with it so a client can point at
        the field rather than showing a sentence beside the wrong one.
        """
        return problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            type_=TYPE_MISSING_ANSWER,
            title="Something still needs answering",
            detail=str(exc),
            keys=exc.keys,
        )

    @app.exception_handler(RunConflictError)
    def _conflict(request: Request, exc: RunConflictError) -> JSONResponse:
        """The request is fine; its timing is not.

        Answering a run that is no longer waiting, cancelling one that has finished. 409
        rather than 400 because there is nothing to correct and nothing to retry — the
        world moved.
        """
        return problem(
            status_code=status.HTTP_409_CONFLICT,
            type_=TYPE_CONFLICT,
            title="That is no longer possible",
            detail=str(exc),
        )

    @app.exception_handler(QueueFullError)
    def _too_busy(request: Request, exc: QueueFullError) -> JSONResponse:
        """More runs are waiting than the queue holds.

        Its own type, and not a quota: this is the only one of the three refusals that
        clears on its own in a minute, so it is the only one where "try again shortly" is
        the right thing to tell somebody.
        """
        response = problem(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            type_=TYPE_BUSY,
            title="Too many runs at once",
            detail="Plantopia is working through a queue. Try again in a minute.",
        )
        response.headers["Retry-After"] = "60"
        return response

    @app.exception_handler(QuotaExceededError)
    def _quota(request: Request, exc: QuotaExceededError) -> JSONResponse:
        """This account has used its allowance.

        The numbers travel as fields rather than inside the sentence, so an interface can
        render "18 of 20 used, resets on the 1st" without parsing prose.
        """
        return problem(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            type_=TYPE_QUOTA_EXCEEDED,
            title="Monthly allowance reached",
            detail="This account has used its runs for the current period.",
            limit=exc.limit,
            used=exc.used,
            resets_at=exc.resets_at.isoformat(),
        )

    @app.exception_handler(DailyCapReachedError)
    def _daily_cap(request: Request, exc: DailyCapReachedError) -> JSONResponse:
        """Everybody together has reached the day's spend.

        Its own type because the person can do nothing about it, and telling them to wait
        for their monthly period would be advice that does not apply.
        """
        return problem(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            type_=TYPE_DAILY_CAP,
            title="Temporarily unavailable",
            detail="Plantopia has reached its spending limit for today. Try again tomorrow.",
            resets_at=exc.resets_at.isoformat(),
        )

    @app.exception_handler(RateLimitedError)
    def _rate_limited(request: Request, exc: RateLimitedError) -> JSONResponse:
        """Too many attempts from one source.

        ``Retry-After`` as well as the field, because it is the header a client library
        already knows how to obey.
        """
        response = problem(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            type_=TYPE_RATE_LIMITED,
            title="Too many attempts",
            detail="Too many attempts from this source. Wait and try again.",
            retry_after_seconds=exc.retry_after_seconds,
        )
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response

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

    @app.exception_handler(ExportTooLargeError)
    def _export_too_large(request: Request, exc: ExportTooLargeError) -> JSONResponse:
        """An account holding more than can be built in one request.

        A refusal rather than a truncated archive: half of somebody's data in a file
        labelled as all of it is worse than being told to ask for help.
        """
        return problem(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            type_=TYPE_INVALID_REQUEST,
            title="That is too much to export at once",
            detail=str(exc),
        )

    @app.exception_handler(ConfirmationError)
    def _refused_deletion(request: Request, exc: ConfirmationError) -> JSONResponse:
        """A deletion that was not confirmed properly.

        Says which of the two was wrong, unlike a sign-in. The caller is already
        authenticated as this account, so telling them their password was mistyped reveals
        nothing the session does not already establish — and being vague here would mean
        somebody retrying a correct password against a mistyped confirmation forever.
        """
        return problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            type_=TYPE_INVALID_REQUEST,
            title="That was not confirmed",
            detail=str(exc),
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
    @app.exception_handler(PasswordChangeError)
    def _registration(
        request: Request, exc: RegistrationError | PasswordChangeError
    ) -> JSONResponse:
        """A request the caller can fix: a password below the minimum, a privacy notice not
        agreed to, or a current password that does not match.

        Two exception families, one handler, because the answer is the same shape and a
        second copy of it would be a second place for the `errors` contract to drift.

        The detail is safe to return because neither refusal depends on whether the address
        is registered — they are decided before anything is looked up.

        Where the refusal knows which part of the request was at fault, it is named in the
        same `errors` shape a malformed body produces, so a client has one way to put a
        message on a control rather than one per status code.
        """
        named = [{"location": ["body", exc.field], "message": str(exc)}] if exc.field else None
        return problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            type_=TYPE_INVALID_REQUEST,
            title="Invalid request",
            detail=str(exc),
            **({"errors": named} if named else {}),
        )

    @app.exception_handler(ResetError)
    def _bad_reset_link(request: Request, exc: ResetError) -> JSONResponse:
        """A reset link that cannot be honoured, answered like a verification one."""
        return problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            type_=TYPE_INVALID_LINK,
            title="This link cannot be used",
            detail="The link is invalid, has expired, or has already been used. Request a new one.",
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
