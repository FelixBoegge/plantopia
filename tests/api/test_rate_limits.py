"""How often one source may hammer the unauthenticated endpoints.

The counters live in process memory and are shared by every test in the run; the autouse
fixture in the root conftest clears them between tests. That sharing is also the limitation
the module documents: two workers permit twice the limit.
"""

import pytest

from api import dependencies, errors
from api.rate_limit import window
from core.config import Settings
from tests.api.test_registration import RecordingMailer
from tests.people import make_user
from tests.secrets import TEST_JWT_SECRET

PASSWORD = "a-long-enough-password"
ADDRESS = "ada@example.com"


@pytest.fixture
def api_settings():
    """A low limit, so the tests do not have to issue dozens of requests to reach it."""
    return Settings(
        _env_file=None,
        openrouter_api_key="sk-test",
        jwt_secret=TEST_JWT_SECRET,
        secure_cookies=False,
        auth_rate_limit=3,
        auth_rate_window_seconds=300,
    )


@pytest.fixture
def mailer(client):
    recorder = RecordingMailer()
    client.app.dependency_overrides[dependencies.mailer_dep] = lambda: recorder
    return recorder


def _without_the_countdown(response) -> dict:
    """The refusal minus ``retry_after_seconds``, which counts down with the clock.

    It varies between two refusals taken a moment apart, and it varies for reasons that
    have nothing to do with whether an address is registered — which is the only thing this
    comparison is about.
    """
    return {k: v for k, v in response.json().items() if k != "retry_after_seconds"}


def _login(client, address=ADDRESS, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": address, "password": password})


def test_ordinary_use_is_not_refused(client, db, mailer):
    make_user(db, email=ADDRESS, password=PASSWORD, verified=True)
    db.commit()

    for _ in range(3):
        assert _login(client).status_code == 200


def test_hammering_sign_in_is_refused(client, db, mailer, api_settings):
    make_user(db, email=ADDRESS, password=PASSWORD, verified=True)
    db.commit()
    for _ in range(api_settings.auth_rate_limit):
        _login(client)

    response = _login(client)

    assert response.status_code == 429
    assert response.json()["type"] == errors.TYPE_RATE_LIMITED


def test_the_refusal_says_when_to_retry(client, db, mailer, api_settings):
    for _ in range(api_settings.auth_rate_limit):
        _login(client)

    response = _login(client)

    assert int(response.headers["Retry-After"]) > 0
    assert response.json()["retry_after_seconds"] > 0


def test_the_limit_does_not_say_who_exists(client, db, mailer, api_settings):
    """Keyed on the source, never the address. Keying on the address would make the limit
    itself the oracle the identical refusals exist to avoid.
    """
    make_user(db, email=ADDRESS, password=PASSWORD, verified=True)
    db.commit()

    for _ in range(api_settings.auth_rate_limit):
        _login(client, address="nobody@example.com")
    refused_registered = _login(client, address=ADDRESS)

    window.forget()
    for _ in range(api_settings.auth_rate_limit):
        _login(client, address=ADDRESS)
    refused_unregistered = _login(client, address="nobody@example.com")

    assert refused_registered.status_code == refused_unregistered.status_code
    assert _without_the_countdown(refused_registered) == _without_the_countdown(
        refused_unregistered
    )


def test_registering_is_limited_too(client, mailer, api_settings):
    body = {"email": ADDRESS, "password": PASSWORD, "accepted_privacy_notice": True}
    for _ in range(api_settings.auth_rate_limit):
        client.post("/api/v1/auth/register", json=body)

    assert client.post("/api/v1/auth/register", json=body).status_code == 429


def test_requesting_a_reset_is_limited_too(client, mailer, api_settings):
    """Otherwise the endpoint is a way to mail somebody else repeatedly."""
    body = {"email": ADDRESS}
    for _ in range(api_settings.auth_rate_limit):
        client.post("/api/v1/auth/reset/request", json=body)

    assert client.post("/api/v1/auth/reset/request", json=body).status_code == 429


def test_the_three_endpoints_share_one_budget(client, mailer, api_settings):
    """Somebody alternating between them is one source hammering, not three."""
    client.post("/api/v1/auth/reset/request", json={"email": ADDRESS})
    client.post(
        "/api/v1/auth/register",
        json={"email": ADDRESS, "password": PASSWORD, "accepted_privacy_notice": True},
    )
    _login(client)

    assert _login(client).status_code == 429


def test_a_refused_attempt_does_not_extend_the_window(client, mailer, api_settings):
    """Raising before recording. Otherwise a client that keeps trying can never get back
    in, which turns a rate limit into a ban.
    """
    for _ in range(api_settings.auth_rate_limit):
        _login(client)
    first_refusal = int(_login(client).headers["Retry-After"])

    for _ in range(5):
        _login(client)
    later_refusal = int(_login(client).headers["Retry-After"])

    assert later_refusal <= first_refusal


def test_verifying_and_refreshing_are_not_limited(client, mailer, api_settings):
    """They are cheap and a signed-in person hits refresh legitimately. Limiting them buys
    nothing and breaks a long session.
    """
    for _ in range(api_settings.auth_rate_limit + 3):
        response = client.post("/api/v1/auth/verify", json={"token": "whatever"})

    assert response.status_code != 429
