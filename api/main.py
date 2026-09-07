"""The application factory.

Built by a function rather than at import time so tests can construct one with their own
dependency overrides, and so nothing reads configuration merely because the module was
imported.

**There is deliberately no module-level ``app``.** One existed briefly, and it undid the
whole point: importing this module constructed ``Settings``, so the moment a required
setting had no default, every test collection failed on configuration rather than on
anything it was testing. Run it as a factory:

    uvicorn api.main:create_app --factory
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import errors
from core.config import Settings, get_settings
from runs import sweeper
from runs.bus import bus


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API.

    Every route is mounted beneath the configured prefix, so a later incompatible version
    can be served alongside this one instead of replacing it underneath a running client.
    """
    settings = settings or get_settings()
    _configure_logging(settings)
    app = FastAPI(
        title="Plantopia",
        version="1",
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=_sweeping(settings),
    )

    errors.register(app, settings)
    _add_cors(app, settings)

    from api.routers import (
        account,
        auth,
        care,
        chat,
        diagnoses,
        health,
        photos,
        plants,
        profile,
        runs,
    )

    routers = (
        health.router,
        auth.router,
        account.router,
        plants.router,
        chat.router,
        care.router,
        diagnoses.router,
        profile.router,
        photos.router,
        runs.router,
    )
    for router in routers:
        app.include_router(router, prefix=settings.api_prefix)

    return app


def _sweeping(settings: Settings):
    """A lifespan that runs the abandoned-run sweeper alongside the application.

    In this process because there is one process; the executor and the event bus are here
    for the same reason. Whether that survives a second process is the deployment change's
    question — `M28` already constrains it the same way.

    A daemon thread, stopped on shutdown so a reload does not leave one behind per restart.
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        if not settings.run_sweeper_enabled:
            yield
            return

        stop = threading.Event()
        thread = threading.Thread(
            target=sweeper.run_periodically,
            args=(settings, bus, stop),
            name="run-sweeper",
            daemon=True,
        )
        thread.start()
        try:
            yield
        finally:
            stop.set()

    return _lifespan


def _configure_logging(settings: Settings) -> None:
    """Make the application's own loggers audible.

    Uvicorn installs handlers for its loggers and leaves the root at ``WARNING``, so
    anything this project logs below that vanishes — including the console mailer, which is
    where a developer reads the verification link out of. Configured here rather than in a
    ``__main__`` because the application is started through a factory and there is no
    ``__main__`` of ours to put it in.

    Adds a handler only when nothing has configured one, so a deployment that installs its
    own logging is not overruled by importing this.
    """
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    else:
        root.setLevel(settings.log_level)


def _add_cors(app: FastAPI, settings: Settings) -> None:
    """Permit the configured origins, and no others.

    Skipped entirely when nothing is configured: adding the middleware with an empty list
    would be a no-op that reads like a policy. The absence of the middleware is the
    policy — no cross-origin browser client is expected until the frontend exists.
    """
    origins = settings.allowed_origins
    if not origins:
        return

    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
