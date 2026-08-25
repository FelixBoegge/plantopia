"""Which endpoints need a session, and what a refusal tells the client.

The table is checked against the application's own routing table, so a route added later
cannot quietly default to open — the test fails until somebody has decided which list it
belongs on.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from api import dependencies, errors
from api.main import create_app
from core.blobs import PostgresBlobStore
from identity.tokens import ALGORITHM, issue_access_token
from tests.people import make_user

# Everything reachable without signing in, and why. Anything not here needs a session.
OPEN = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/verify"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/ready"),
}

# Not endpoints. The schema is public by design and carries no data.
DOCUMENTATION = {"/api/v1/docs", "/api/v1/openapi.json", "/api/v1/docs/oauth2-redirect"}

# The detail the session dependency refuses with, as opposed to sign-in refusing credentials.
NEEDS_A_SESSION = "This endpoint needs a signed-in account."


@pytest.fixture
def anonymous(db, api_settings):
    """A client with no session and no owner override — what a stranger has."""
    app = create_app(api_settings)
    app.dependency_overrides[dependencies.session_dep] = lambda: db
    app.dependency_overrides[dependencies.settings_dep] = lambda: api_settings
    app.dependency_overrides[dependencies.blob_store] = lambda: PostgresBlobStore(db)
    with TestClient(app) as client:
        yield client


def _routes(app):
    """Every endpoint the application actually serves.

    Read from the generated schema rather than by walking ``app.routes``, which nests
    included routers in a wrapper whose shape is a FastAPI internal — a walk that works
    today and silently yields nothing after an upgrade is worse than no test at all.
    """
    for path, operations in app.openapi()["paths"].items():
        if path in DOCUMENTATION:
            continue
        for method in operations:
            yield method.upper(), path


def _call(client, method: str, path: str):
    """Issue the request with placeholder path parameters.

    The values do not have to resolve: a route that needs a session must refuse before it
    ever looks one up, so a nonexistent identifier is the right probe.
    """
    concrete = path
    while "{" in concrete:
        head, _, rest = concrete.partition("{")
        _, _, tail = rest.partition("}")
        concrete = f"{head}{uuid4()}{tail}"
    return client.request(method, concrete, json={})


def test_every_route_is_classified(anonymous):
    """The table and the application must agree, so a new route cannot default to open."""
    routed = set(_routes(anonymous.app))

    assert routed >= OPEN, f"the table names routes that do not exist: {OPEN - routed}"
    assert routed - OPEN, "no protected routes were found; the walk is reading nothing"


def test_protected_routes_refuse_a_stranger(anonymous):
    """Every route not on the open list answers 401 without a session."""
    refused = []
    for method, path in _routes(anonymous.app):
        if (method, path) in OPEN:
            continue
        response = _call(anonymous, method, path)
        if response.status_code != 401:
            refused.append((method, path, response.status_code))

    assert refused == []


def test_open_routes_do_not_ask_for_a_session(anonymous):
    """Registering and signing in cannot require being signed in, and a health probe that
    needs credentials is a health probe nothing can call.
    """
    asked = []
    for method, path in sorted(OPEN):
        response = _call(anonymous, method, path)
        # Sign-in refusing empty credentials is not the same as demanding a session, so the
        # detail is what distinguishes them rather than the status.
        if response.status_code == 401 and NEEDS_A_SESSION in response.text:
            asked.append((method, path))

    assert asked == []


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_a_valid_token_reaches_the_handler(anonymous, db, api_settings):
    user = make_user(db)
    db.commit()
    token = issue_access_token(user_id=user.id, secret=api_settings.jwt_secret, lifetime_minutes=15)

    response = anonymous.get("/api/v1/plants", headers=_bearer(token))

    assert response.status_code == 200


def test_an_expired_token_says_so(anonymous, api_settings):
    """The client refreshes. A refusal it cannot distinguish from a bad token would make it
    sign the person out every fifteen minutes.
    """
    expired = issue_access_token(
        user_id=uuid4(), secret=api_settings.jwt_secret, lifetime_minutes=-1
    )

    response = anonymous.get("/api/v1/plants", headers=_bearer(expired))

    assert response.status_code == 401
    assert response.json()["type"] == errors.TYPE_SESSION_EXPIRED


def test_a_malformed_token_says_sign_in_again(anonymous):
    response = anonymous.get("/api/v1/plants", headers=_bearer("not-a-token"))

    assert response.status_code == 401
    assert response.json()["type"] == errors.TYPE_UNAUTHENTICATED


def test_the_two_refusals_are_distinguishable(anonymous, api_settings):
    """The property a client depends on: which of "refresh" and "sign in again" to do."""
    expired = anonymous.get(
        "/api/v1/plants",
        headers=_bearer(
            issue_access_token(user_id=uuid4(), secret=api_settings.jwt_secret, lifetime_minutes=-1)
        ),
    )
    malformed = anonymous.get("/api/v1/plants", headers=_bearer("nonsense"))

    assert expired.json()["type"] != malformed.json()["type"]


def test_a_token_signed_with_another_secret_is_refused(anonymous):
    """Anybody can mint a JWT. Only ours is signed with our key."""
    forged = jwt.encode(
        {
            "sub": str(uuid4()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
        },
        "a-different-secret-entirely-long-enough",
        algorithm=ALGORITHM,
    )

    response = anonymous.get("/api/v1/plants", headers=_bearer(forged))

    assert response.status_code == 401
    assert response.json()["type"] == errors.TYPE_UNAUTHENTICATED


def test_a_token_naming_no_owner_is_refused(anonymous, api_settings):
    forged = jwt.encode(
        {
            "sub": "not-an-identifier",
            "exp": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
        },
        api_settings.jwt_secret,
        algorithm=ALGORITHM,
    )

    response = anonymous.get("/api/v1/plants", headers=_bearer(forged))

    assert response.status_code == 401


def test_a_scheme_other_than_bearer_is_refused(anonymous, db, api_settings):
    user = make_user(db)
    db.commit()
    token = issue_access_token(user_id=user.id, secret=api_settings.jwt_secret, lifetime_minutes=15)

    response = anonymous.get("/api/v1/plants", headers={"Authorization": f"Basic {token}"})

    assert response.status_code == 401
