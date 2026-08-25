"""One shape for every failure.

Clients branch on ``type``, which makes it part of the interface. These tests are what
stop a handler quietly returning a bare string, or an exception message carrying a query
or a fragment of somebody's data out to a client.
"""

from fastapi import APIRouter

from api import errors
from api.main import create_app
from core.ids import new_id

PROBLEM_FIELDS = {"type", "title", "status"}


def test_a_missing_resource_carries_the_shared_shape(client):
    response = client.get(f"/api/v1/plants/{new_id()}")

    body = response.json()
    assert set(body) >= PROBLEM_FIELDS
    assert body["type"] == errors.TYPE_NOT_FOUND
    assert body["status"] == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_a_malformed_body_names_the_fields_it_rejected(client, seeded):
    response = client.patch(f"/api/v1/plants/{seeded['plant_id']}", json={"nom": "wrong"})

    body = response.json()
    assert body["type"] == errors.TYPE_INVALID_REQUEST
    assert body["status"] == 422
    assert any("name" in error["location"] for error in body["errors"])


def test_validation_errors_do_not_echo_the_input(client, seeded):
    """FastAPI's raw errors can carry the offending value, which here could be somebody's
    chat message."""
    secret = "my-private-note-12345"
    response = client.post(
        f"/api/v1/plants/{seeded['plant_id']}/messages", json={"content": "", "extra": secret}
    )

    assert secret not in response.text


def test_an_unhandled_failure_reveals_nothing(api_settings, caplog):
    """The cause goes to the log, not to the client."""
    app = create_app(api_settings)
    router = APIRouter()

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("connection string postgresql://user:hunter2@host/db")

    app.include_router(router, prefix=api_settings.api_prefix)

    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get(f"{api_settings.api_prefix}/boom")

    body = response.json()
    assert response.status_code == 500
    assert body["type"] == errors.TYPE_INTERNAL
    assert "hunter2" not in response.text
    assert "postgresql://" not in response.text
    assert "Traceback" not in response.text
    assert "hunter2" in caplog.text, (
        "the cause must reach the log even though it does not reach the client"
    )
