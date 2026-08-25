"""The application factory.

Built by a function rather than at import time so tests can construct one with their own
dependency overrides, and so nothing connects to a database merely because the module was
imported.
"""

from fastapi import FastAPI

from api import errors
from core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API.

    Every route is mounted beneath the configured prefix, so a later incompatible version
    can be served alongside this one instead of replacing it underneath a running client.
    """
    settings = settings or get_settings()
    app = FastAPI(
        title="Plantopia",
        version="1",
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    errors.register(app)
    _add_cors(app, settings)

    from api.routers import care, chat, health, photos, plants, profile

    routers = (
        health.router,
        plants.router,
        chat.router,
        care.router,
        profile.router,
        photos.router,
    )
    for router in routers:
        app.include_router(router, prefix=settings.api_prefix)

    return app


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


app = create_app()
