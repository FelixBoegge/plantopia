"""Changing your password while signed in.

The reset flow exists for somebody who cannot sign in and proves who they are through their
email. This is the other half: somebody who is already signed in, proving who they are with
the password they are replacing. Neither substitutes for the other — you cannot ask for the
old password from a person who has forgotten it, and you should not make a signed-in person
wait on an email to do something they are already authenticated for.

The property carrying the most weight is the one about sessions: every *other* session ends
and this one does not. Ending them all would sign somebody out for the crime of tidying up
their own password; ending none would leave whoever prompted the change still signed in.
"""

import pytest
from sqlalchemy import select

from data.models import RefreshToken, User
from identity.passwords import hash_password
from identity.passwords import verify as verify_password

PASSWORD = "a-long-enough-password"
NEW_PASSWORD = "a-completely-different-one"


@pytest.fixture
def owner_password(db, owner) -> str:
    """The signed-in owner, with a password they can actually re-enter.

    The shared `owner` fixture carries the unusable sentinel, because most tests only need
    somebody to scope records to.
    """
    db.get(User, owner).password_hash = hash_password(PASSWORD)
    db.flush()
    return PASSWORD


def _change(client, **overrides):
    body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD} | overrides
    return client.post("/api/v1/auth/password", json=body)


def _live_tokens(db, user_id) -> int:
    return len(
        db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        ).all()
    )


def test_the_password_changes(client, db, owner, owner_password):
    assert _change(client).status_code == 204

    db.expire_all()
    assert verify_password(NEW_PASSWORD, db.get(User, owner).password_hash)


def test_the_old_password_stops_working(client, db, owner, owner_password):
    _change(client)

    db.expire_all()
    assert not verify_password(PASSWORD, db.get(User, owner).password_hash)


def test_a_wrong_current_password_is_refused(client, db, owner, owner_password):
    response = _change(client, current_password="not-the-right-one-at-all")

    assert response.status_code == 400
    db.expire_all()
    assert verify_password(PASSWORD, db.get(User, owner).password_hash)


def test_a_wrong_current_password_says_which_field(client, owner_password):
    """So the screen can put the message under the box it is about."""
    response = _change(client, current_password="not-the-right-one-at-all")

    [rejected] = response.json()["errors"]
    assert rejected["location"] == ["body", "current_password"]


def test_a_new_password_below_the_minimum_is_refused(
    client, db, owner, api_settings, owner_password
):
    short = "x" * (api_settings.minimum_password_length - 1)

    response = _change(client, new_password=short)

    assert response.status_code == 400
    assert str(api_settings.minimum_password_length) in response.json()["detail"]
    db.expire_all()
    assert verify_password(PASSWORD, db.get(User, owner).password_hash)


def test_a_weak_new_password_says_which_field(client, api_settings, owner_password):
    """The new box, not the current one — the same message on the wrong field would send
    somebody to correct a password that was right."""
    short = "x" * (api_settings.minimum_password_length - 1)

    response = _change(client, new_password=short)

    [rejected] = response.json()["errors"]
    assert rejected["location"] == ["body", "new_password"]


def test_it_cannot_be_reached_without_a_session(client, owner_password):
    """No email address anywhere in this: the only account it can change is the one the
    request is already authenticated as."""
    client.headers.pop("Authorization", None)

    assert _change(client).status_code == 401


def test_every_other_session_ends(client, db, owner, api_settings, owner_password):
    """Whoever prompted the change must not still be signed in when it is over."""
    from identity import sessions

    for _ in range(3):
        sessions.start(db, user_id=owner, settings=api_settings)
    db.flush()
    before = _live_tokens(db, owner)
    assert before >= 3

    _change(client)

    db.expire_all()
    assert _live_tokens(db, owner) < before


def test_this_session_survives_it(client, db, owner, api_settings, owner_password):
    """Ending every session would sign somebody out for tidying up their own password."""
    from identity import sessions

    mine = sessions.start(db, user_id=owner, settings=api_settings)
    db.flush()

    client.cookies.set("plantopia_refresh", mine.refresh_token)
    assert _change(client).status_code == 204

    db.expire_all()
    kept = db.scalars(
        select(RefreshToken).where(RefreshToken.user_id == owner, RefreshToken.revoked_at.is_(None))
    ).all()
    assert [token.family_id for token in kept] == [mine.family_id]
