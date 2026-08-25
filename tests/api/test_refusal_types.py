"""Every refusal is distinguishable from every other, by machine.

A client has to decide what to do next, and each of these calls for something different:
refresh, sign in, wait for the period, wait for tomorrow, wait a few minutes, or give up on
a resource that is not there. Prose cannot carry that decision.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api import errors
from api.main import create_app
from api.rate_limit import RateLimitedError
from core.ids import new_id
from data.repositories.errors import RecordNotFoundError
from identity.accounts import AuthenticationError
from services.limits import DailyCapReachedError, QuotaExceededError

RESETS = datetime(2026, 4, 1, tzinfo=UTC)

# Every refusal this application can produce, and what raises it. Routes are added so the
# handler mapping is exercised rather than the exception classes being read directly.
REFUSALS = {
    "not-found": RecordNotFoundError("no such plant"),
    "unauthenticated": AuthenticationError("those credentials were not accepted"),
    "quota": QuotaExceededError(limit=20, used=20, resets_at=RESETS),
    "daily-cap": DailyCapReachedError(cap_usd=5.0, spent_usd=5.1, resets_at=RESETS),
    "rate-limit": RateLimitedError(retry_after_seconds=42),
}


def _raiser(exception):
    """A parameterless handler that raises one exception.

    Parameterless deliberately: a closure over the loop variable binds late, and giving the
    handler a default argument instead makes FastAPI read it as a query parameter.
    """

    def _raise() -> None:
        raise exception

    return _raise


@pytest.fixture
def raising_client(api_settings):
    """An application with one route per refusal, doing nothing but raising it."""
    app = create_app(api_settings)
    for label, exception in REFUSALS.items():
        app.add_api_route(f"/raise/{label}", _raiser(exception), methods=["GET"])

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _type_of(client, label: str) -> str:
    return client.get(f"/raise/{label}").json()["type"]


def test_every_refusal_has_its_own_type(raising_client):
    types = {label: _type_of(raising_client, label) for label in REFUSALS}

    assert len(set(types.values())) == len(REFUSALS), f"two refusals share a type: {types}"


def test_a_quota_and_the_daily_cap_are_not_the_same_refusal(raising_client):
    """The person can do something about one and nothing about the other."""
    assert _type_of(raising_client, "quota") == errors.TYPE_QUOTA_EXCEEDED
    assert _type_of(raising_client, "daily-cap") == errors.TYPE_DAILY_CAP


def test_a_rate_limit_is_neither_of_them(raising_client):
    assert _type_of(raising_client, "rate-limit") == errors.TYPE_RATE_LIMITED


def test_not_being_signed_in_is_its_own_thing(raising_client):
    assert _type_of(raising_client, "unauthenticated") == errors.TYPE_UNAUTHENTICATED


def test_a_missing_resource_is_not_a_limit(raising_client):
    assert _type_of(raising_client, "not-found") == errors.TYPE_NOT_FOUND


def test_the_quota_refusal_carries_the_numbers_an_interface_needs(raising_client):
    body = raising_client.get("/raise/quota").json()

    assert body["limit"] == 20
    assert body["used"] == 20
    assert body["resets_at"] == RESETS.isoformat()


def test_the_cap_refusal_says_when_it_lifts(raising_client):
    assert raising_client.get("/raise/daily-cap").json()["resets_at"] == RESETS.isoformat()


def test_the_rate_limit_refusal_carries_a_retry_after_header(raising_client):
    response = raising_client.get("/raise/rate-limit")

    assert response.headers["Retry-After"] == "42"


def test_every_refusal_keeps_the_shared_shape(raising_client):
    """One envelope, whatever the failure. A client parses one thing."""
    for label in REFUSALS:
        response = raising_client.get(f"/raise/{label}")
        body = response.json()

        assert set(body) >= {"type", "title", "status"}, label
        assert body["status"] == response.status_code, label
        assert response.headers["content-type"].startswith("application/problem+json"), label


def test_the_statuses_say_whose_problem_it_is(raising_client):
    """429 for the two the caller can wait out, 503 for the one that is ours."""
    assert raising_client.get("/raise/quota").status_code == 429
    assert raising_client.get("/raise/rate-limit").status_code == 429
    assert raising_client.get("/raise/daily-cap").status_code == 503
    assert raising_client.get("/raise/unauthenticated").status_code == 401
    assert raising_client.get("/raise/not-found").status_code == 404


def test_no_refusal_leaks_an_identifier_it_was_given(raising_client, api_settings):
    """A not-found that echoed the identifier would confirm the shape of what was asked
    for; more importantly, nothing here should be repeating input back at all.
    """
    identifier = str(new_id())
    app = create_app(api_settings)

    def _raise():
        raise RecordNotFoundError(f"no plant {identifier}")

    app.add_api_route("/raise/echo", _raise, methods=["GET"])
    with TestClient(app, raise_server_exceptions=False) as client:
        assert identifier not in client.get("/raise/echo").text
