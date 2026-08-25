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

from data.repositories.errors import RecordNotFoundError

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/problem+json"

# Stable identifiers. A client branches on these, so they are as much a contract as the
# status codes beside them.
TYPE_NOT_FOUND = "https://plantopia.example/problems/not-found"
TYPE_INVALID_REQUEST = "https://plantopia.example/problems/invalid-request"
TYPE_INTERNAL = "https://plantopia.example/problems/internal-error"


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
