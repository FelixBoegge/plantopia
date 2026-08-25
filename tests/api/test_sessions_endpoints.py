"""Signing in, staying signed in, and signing out.

The cookie attributes are asserted individually rather than as a rendered header, because
each of them is a separate decision and losing any one of them is silent.
"""

import pytest
from sqlalchemy import select

from api import cookies, dependencies, errors
from core.config import Settings
from data.models import RefreshToken
from identity.tokens import fingerprint, read_access_token
from tests.people import make_user
from tests.secrets import TEST_JWT_SECRET

PASSWORD = "a-long-enough-password"
ADDRESS = "ada@example.com"


@pytest.fixture
def account(db):
    user = make_user(db, email=ADDRESS, password=PASSWORD, verified=True)
    db.commit()
    return user


def _login(client, **overrides):
    body = {"email": ADDRESS, "password": PASSWORD} | overrides
    return client.post("/api/v1/auth/login", json=body)


def _set_cookie(response) -> str:
    return response.headers["set-cookie"]


def test_signing_in_returns_an_access_token_naming_the_account(client, account, api_settings):
    response = _login(client)

    assert response.status_code == 200
    body = response.json()
    assert read_access_token(body["access_token"], secret=api_settings.jwt_secret) == account.id


def test_signing_in_says_how_long_the_access_token_lasts(client, account, api_settings):
    """The client refreshes ahead of expiry, which it cannot do without being told."""
    body = _login(client).json()

    assert body["expires_in_seconds"] == api_settings.access_token_minutes * 60
    assert body["token_type"] == "bearer"


def test_the_refresh_token_is_not_in_the_body(client, account, db):
    """It travels as an httpOnly cookie. Putting it in the body as well would hand it to
    any script that can read the response.
    """
    response = _login(client)

    stored = db.scalar(select(RefreshToken).where(RefreshToken.user_id == account.id))
    assert stored is not None
    assert fingerprint(response.json()["access_token"]) != stored.token_hash
    assert cookies.NAME not in response.text


def test_the_refresh_cookie_is_set(client, account):
    response = _login(client)

    assert cookies.NAME in response.cookies


def test_the_refresh_cookie_cannot_be_read_by_a_script(client, account):
    assert "httponly" in _set_cookie(_login(client)).lower()


def test_the_refresh_cookie_is_not_sent_to_other_sites(client, account):
    assert "samesite=strict" in _set_cookie(_login(client)).lower()


def test_the_refresh_cookie_is_confined_to_the_auth_routes(client, account, api_settings):
    """A refresh token attached to every request is a refresh token in every log."""
    assert f"path={cookies.path_for(api_settings)}" in _set_cookie(_login(client)).lower()


def test_the_refresh_cookie_is_marked_secure_when_it_should_be(db, account):
    """Asserted against settings that leave it on, since the client fixture turns it off to
    keep a plain-http cookie jar working.
    """
    from fastapi.testclient import TestClient

    from api.main import create_app

    settings = Settings(
        _env_file=None,
        openrouter_api_key="sk-test",
        jwt_secret=TEST_JWT_SECRET,
        secure_cookies=True,
    )
    app = create_app(settings)
    app.dependency_overrides[dependencies.session_dep] = lambda: db
    app.dependency_overrides[dependencies.settings_dep] = lambda: settings

    with TestClient(app) as secure_client:
        response = _login(secure_client)

    assert "secure" in _set_cookie(response).lower()


def test_an_unverified_account_cannot_sign_in(client, db):
    make_user(db, email="unverified@example.com", password=PASSWORD, verified=False)
    db.commit()

    response = _login(client, email="unverified@example.com")

    assert response.status_code == 401
    assert cookies.NAME not in response.cookies


def test_an_unverified_account_gets_no_session(client, db):
    user = make_user(db, email="unverified@example.com", password=PASSWORD, verified=False)
    db.commit()

    _login(client, email="unverified@example.com")

    assert db.scalar(select(RefreshToken).where(RefreshToken.user_id == user.id)) is None


def test_a_wrong_password_and_an_unknown_address_answer_identically(client, account):
    """Otherwise sign-in is a way to ask who has an account here."""
    wrong = _login(client, password="not-the-right-password")
    unknown = _login(client, email="nobody@example.com")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_an_unverified_account_answers_the_same_way_too(client, db, account):
    """The third refusal joins the other two. On its own it would say whether somebody has
    read their email.
    """
    make_user(db, email="unverified@example.com", password=PASSWORD, verified=False)
    db.commit()

    unverified = _login(client, email="unverified@example.com")
    unknown = _login(client, email="nobody@example.com")

    assert unverified.json() == unknown.json()


def test_a_refused_sign_in_carries_the_unauthenticated_type(client, account):
    response = _login(client, password="wrong-password-entirely")

    assert response.json()["type"] == errors.TYPE_UNAUTHENTICATED


def test_refreshing_issues_a_new_access_token(client, account, api_settings):
    _login(client)

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert (
        read_access_token(response.json()["access_token"], secret=api_settings.jwt_secret)
        == account.id
    )


def test_refreshing_replaces_the_cookie(client, account):
    before = _login(client).cookies[cookies.NAME]

    response = client.post("/api/v1/auth/refresh")

    assert response.cookies[cookies.NAME] != before


def test_the_presented_refresh_token_stops_working(client, account):
    """A rotated token presented again looks exactly like a stolen one, and is treated as
    one — which is why the client does not retry a refresh.
    """
    presented = _login(client).cookies[cookies.NAME]
    client.post("/api/v1/auth/refresh")

    response = client.post("/api/v1/auth/refresh", cookies={cookies.NAME: presented})

    assert response.status_code == 401


def test_refreshing_without_a_cookie_is_refused(client, account):
    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["type"] == errors.TYPE_UNAUTHENTICATED


def test_reusing_a_token_ends_the_whole_family(client, account):
    presented = _login(client).cookies[cookies.NAME]
    successor = client.post("/api/v1/auth/refresh").cookies[cookies.NAME]

    client.post("/api/v1/auth/refresh", cookies={cookies.NAME: presented})
    response = client.post("/api/v1/auth/refresh", cookies={cookies.NAME: successor})

    assert response.status_code == 401


def test_signing_out_refuses_a_later_refresh(client, account):
    _login(client)

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_signing_out_clears_the_cookie(client, account):
    _login(client)

    client.post("/api/v1/auth/logout")

    assert cookies.NAME not in client.cookies


def test_signing_out_clears_it_at_the_path_it_was_set_on(client, account, api_settings):
    """Cleared with a different path is not cleared at all."""
    _login(client)

    header = _set_cookie(client.post("/api/v1/auth/logout")).lower()

    assert f"path={cookies.path_for(api_settings)}" in header


def test_signing_out_without_a_session_is_still_a_success(client):
    """Signing out is a request to be signed out. Reporting that a token was already
    invalid tells an unauthenticated caller which tokens exist.
    """
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_signing_out_ends_the_family_not_just_the_presented_token(client, account, db):
    _login(client)
    client.post("/api/v1/auth/refresh")

    client.post("/api/v1/auth/logout")

    live = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == account.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.used_at.is_(None),
        )
    ).all()
    assert live == []


def test_signing_in_twice_leaves_both_sessions_working(client, account, api_settings):
    """Families are per sign-in, so a second device does not end the first."""
    from fastapi.testclient import TestClient

    first = _login(client).cookies[cookies.NAME]
    with TestClient(client.app) as second_device:
        _login(second_device)
        assert second_device.post("/api/v1/auth/refresh").status_code == 200

    assert client.post("/api/v1/auth/refresh", cookies={cookies.NAME: first}).status_code == 200
