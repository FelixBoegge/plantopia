"""Liveness and readiness, which are deliberately not the same question."""

from sqlalchemy.exc import OperationalError

from api import dependencies


def test_health_reports_the_process_is_running(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_the_database_is_reachable(client):
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": True}


def test_readiness_fails_while_liveness_still_succeeds(client, api_settings):
    """The distinction is the point: an orchestrator that cannot tell them apart restarts
    a container which is merely waiting for its database, turning a delay into a crash
    loop."""

    class _Unreachable:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    client.app.dependency_overrides[dependencies.session_dep] = lambda: _Unreachable()

    ready = client.get("/api/v1/ready")
    alive = client.get("/api/v1/health")

    assert ready.status_code == 503
    assert ready.json() == {"status": "not ready", "database": False}
    assert alive.status_code == 200
