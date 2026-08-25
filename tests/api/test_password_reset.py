"""Resetting a forgotten password.

Two properties carry the weight: the response never says whether an address has an account,
and using a link ends every session that existed before it.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from api import cookies, dependencies, errors
from data.models import EmailToken, RefreshToken, User
from identity.passwords import verify as verify_password
from identity.tokens import fingerprint
from tests.api.test_registration import RecordingMailer
from tests.people import make_user

OLD_PASSWORD = "the-password-they-forgot"
NEW_PASSWORD = "a-completely-different-one"
ADDRESS = "ada@example.com"


@pytest.fixture
def mailer(client):
    recorder = RecordingMailer()
    client.app.dependency_overrides[dependencies.mailer_dep] = lambda: recorder
    return recorder


@pytest.fixture
def account(db):
    user = make_user(db, email=ADDRESS, password=OLD_PASSWORD, verified=True)
    db.commit()
    return user


def _request(client, address=ADDRESS):
    return client.post("/api/v1/auth/reset/request", json={"email": address})


def _confirm(client, token, password=NEW_PASSWORD):
    return client.post("/api/v1/auth/reset/confirm", json={"token": token, "password": password})


def _link_token(mailer) -> str:
    return mailer.sent[-1].body.split("token=")[1].split()[0]


def test_requesting_sends_a_link(client, account, mailer):
    response = _request(client)

    assert response.status_code == 202
    assert mailer.sent[0].to == ADDRESS
    assert "/reset?token=" in mailer.sent[0].body


def test_an_unregistered_address_answers_identically(client, account, mailer):
    registered = _request(client)

    unregistered = _request(client, "nobody@example.com")

    assert registered.status_code == unregistered.status_code
    assert registered.json() == unregistered.json()


def test_nothing_is_sent_to_an_address_with_no_account(client, mailer):
    _request(client, "nobody@example.com")

    assert mailer.sent == []


def test_nothing_is_written_for_an_address_with_no_account(client, db, mailer):
    """A token row created for a nonexistent account would be a way to ask, by counting."""
    _request(client, "nobody@example.com")

    assert db.scalars(select(EmailToken)).all() == []


def test_the_link_sets_the_new_password(client, db, account, mailer):
    _request(client)

    response = _confirm(client, _link_token(mailer))

    assert response.status_code == 204
    db.expire_all()
    assert verify_password(NEW_PASSWORD, db.get(User, account.id).password_hash)


def test_the_old_password_stops_working(client, db, account, mailer):
    _request(client)
    _confirm(client, _link_token(mailer))

    response = client.post("/api/v1/auth/login", json={"email": ADDRESS, "password": OLD_PASSWORD})

    assert response.status_code == 401


def test_the_new_password_signs_in(client, db, account, mailer):
    _request(client)
    _confirm(client, _link_token(mailer))

    response = client.post("/api/v1/auth/login", json={"email": ADDRESS, "password": NEW_PASSWORD})

    assert response.status_code == 200


def test_the_link_cannot_be_used_twice(client, account, mailer):
    _request(client)
    token = _link_token(mailer)
    _confirm(client, token)

    response = _confirm(client, token, password="yet-another-password")

    assert response.status_code == 400
    assert response.json()["type"] == errors.TYPE_INVALID_LINK


def test_a_second_use_does_not_change_the_password_again(client, db, account, mailer):
    _request(client)
    token = _link_token(mailer)
    _confirm(client, token)

    _confirm(client, token, password="yet-another-password")

    db.expire_all()
    assert verify_password(NEW_PASSWORD, db.get(User, account.id).password_hash)


def test_an_expired_link_is_refused(client, db, account, mailer):
    _request(client)
    token = _link_token(mailer)
    stored = db.scalar(select(EmailToken).where(EmailToken.token_hash == fingerprint(token)))
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    response = _confirm(client, token)

    assert response.status_code == 400
    db.expire_all()
    assert verify_password(OLD_PASSWORD, db.get(User, account.id).password_hash)


def test_requesting_again_retires_the_first_link(client, account, mailer):
    """So a link found later cannot be used against the person who abandoned it."""
    _request(client)
    first = _link_token(mailer)
    _request(client)
    second = _link_token(mailer)

    assert _confirm(client, first).status_code == 400
    assert _confirm(client, second).status_code == 204


def test_resetting_ends_every_existing_session(client, db, account, mailer):
    signed_in = client.post("/api/v1/auth/login", json={"email": ADDRESS, "password": OLD_PASSWORD})
    assert signed_in.status_code == 200
    _request(client)

    _confirm(client, _link_token(mailer))

    live = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == account.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.used_at.is_(None),
        )
    ).all()
    assert live == []


def test_a_session_from_before_the_reset_cannot_refresh(client, db, account, mailer):
    """The property the database check stands for, asserted through the interface."""
    client.post("/api/v1/auth/login", json={"email": ADDRESS, "password": OLD_PASSWORD})
    _request(client)

    _confirm(client, _link_token(mailer))

    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert cookies.NAME in client.cookies  # the cookie is stale, not cleared — and refused


def test_a_verification_link_cannot_be_used_to_reset_a_password(client, db, mailer):
    """Otherwise proving an address would be enough to take the account."""
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": OLD_PASSWORD,
            "accepted_privacy_notice": True,
        },
    )
    verification = _link_token(mailer)

    response = _confirm(client, verification)

    assert response.status_code == 400


def test_a_password_below_the_minimum_is_refused(client, db, account, mailer, api_settings):
    _request(client)

    response = _confirm(
        client, _link_token(mailer), password="x" * (api_settings.minimum_password_length - 1)
    )

    assert response.status_code == 400
    db.expire_all()
    assert verify_password(OLD_PASSWORD, db.get(User, account.id).password_hash)


def test_a_refused_reset_leaves_the_link_usable(client, db, account, mailer, api_settings):
    """A short password is the person's mistake, not a reason to make them ask again."""
    _request(client)
    token = _link_token(mailer)
    _confirm(client, token, password="short")

    assert _confirm(client, token).status_code == 204


def test_resetting_also_proves_the_address(client, db, mailer):
    """The link only arrives by email, which is exactly what verification asserts. Refusing
    to accept it would leave an account that has proved its address unable to sign in.
    """
    user = make_user(db, email="unverified@example.com", password=OLD_PASSWORD, verified=False)
    db.commit()
    _request(client, "unverified@example.com")

    _confirm(client, _link_token(mailer))

    db.expire_all()
    assert db.get(User, user.id).verified_at is not None
