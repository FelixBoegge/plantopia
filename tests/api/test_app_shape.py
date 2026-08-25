"""The shape of the application itself: versioning, CORS, and request scope."""

from core.config import Settings


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, openrouter_api_key="sk-test", **overrides)


def test_every_route_is_served_beneath_the_version_prefix(client):
    """So that a later incompatible interface can exist alongside this one rather than
    replacing it underneath a running client."""
    paths = client.app.openapi()["paths"]

    assert paths
    assert all(path.startswith("/api/v1") for path in paths), sorted(paths)


def test_no_origin_is_permitted_by_default(client):
    """A permissive default is the kind of thing that ships because nobody had a reason to
    tighten it. Absent configuration, the middleware is not installed at all."""
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_a_configured_origin_is_permitted(db, owner):
    from fastapi.testclient import TestClient

    from api import dependencies
    from api.main import create_app

    settings = _settings(cors_origins="http://localhost:5173")
    app = create_app(settings)
    app.dependency_overrides[dependencies.session_dep] = lambda: db
    app.dependency_overrides[dependencies.current_owner] = lambda: owner

    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_an_unconfigured_origin_is_not_permitted(db, owner):
    from fastapi.testclient import TestClient

    from api import dependencies
    from api.main import create_app

    settings = _settings(cors_origins="http://localhost:5173")
    app = create_app(settings)
    app.dependency_overrides[dependencies.session_dep] = lambda: db
    app.dependency_overrides[dependencies.current_owner] = lambda: owner

    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert response.headers.get("access-control-allow-origin") != "https://evil.example"


def test_origins_are_parsed_from_a_comma_separated_list():
    settings = _settings(cors_origins=" http://a.example , http://b.example ,, ")

    assert settings.allowed_origins == ["http://a.example", "http://b.example"]


def test_each_request_gets_its_own_session(api_settings):
    """Not cached process-wide the way Streamlit's are: a cached service would pin one
    owner into a process serving many, and a session is not safe to share concurrently."""
    from fastapi import APIRouter
    from fastapi.testclient import TestClient

    from api.dependencies import SessionDep
    from api.main import create_app

    seen: list[int] = []
    app = create_app(api_settings)
    router = APIRouter()

    @router.get("/probe")
    def probe(session: SessionDep) -> dict:
        seen.append(id(session))
        return {"ok": True}

    app.include_router(router, prefix=api_settings.api_prefix)

    with TestClient(app) as test_client:
        test_client.get(f"{api_settings.api_prefix}/probe")
        test_client.get(f"{api_settings.api_prefix}/probe")

    assert len(seen) == 2
    assert seen[0] != seen[1]


def test_the_session_is_closed_even_when_a_handler_raises(api_settings):
    """A leak here exhausts the pool after a few dozen failures rather than immediately —
    the kind of fault that only appears under load."""
    from fastapi import APIRouter
    from fastapi.testclient import TestClient

    from api.dependencies import SessionDep
    from api.main import create_app

    captured: list = []
    app = create_app(api_settings)
    router = APIRouter()

    @router.get("/explode")
    def explode(session: SessionDep) -> None:
        captured.append(session)
        raise RuntimeError("boom")

    app.include_router(router, prefix=api_settings.api_prefix)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.get(f"{api_settings.api_prefix}/explode")

    assert captured
    assert not captured[0].is_active or not captured[0].in_transaction()
