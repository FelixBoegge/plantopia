"""Registering, and proving an address.

The properties under test are mostly about what does *not* happen: no password comes back,
no second account is created, and no response differs on whether an address is registered.
Each of those is asserted directly, because each of them fails silently.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from api import dependencies, errors
from core.mail import Message
from data.models import EmailToken, User
from identity import email_tokens
from identity.passwords import verify as verify_password
from identity.tokens import fingerprint
from tests.people import make_user

PASSWORD = "a-long-enough-password"
ADDRESS = "ada@example.com"


class RecordingMailer:
    """Collects what would have been sent."""

    def __init__(self, *, delivers: bool = True) -> None:
        self.sent: list[Message] = []
        self._delivers = delivers

    def send(self, message: Message) -> bool:
        self.sent.append(message)
        return self._delivers


@pytest.fixture
def mailer(client):
    recorder = RecordingMailer()
    client.app.dependency_overrides[dependencies.mailer_dep] = lambda: recorder
    return recorder


def _register(client, **overrides):
    body = {"email": ADDRESS, "password": PASSWORD, "accepted_privacy_notice": True} | overrides
    return client.post("/api/v1/auth/register", json=body)


def _account(db, address=ADDRESS) -> User | None:
    return db.scalar(select(User).where(User.email == address))


def _count(db, address=ADDRESS) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.email == address))


def _token_from(mailer) -> str:
    body = mailer.sent[-1].body
    return body.split("token=")[1].split()[0]


def test_registering_creates_an_unverified_account(client, db, mailer):
    response = _register(client)

    assert response.status_code == 202
    account = _account(db)
    assert account is not None
    assert account.verified_at is None


def test_registering_sends_a_verification_message_to_that_address(client, mailer):
    _register(client)

    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == ADDRESS
    assert "/verify?token=" in mailer.sent[0].body


def test_the_response_carries_neither_the_password_nor_its_hash(client, db, mailer):
    response = _register(client)

    assert PASSWORD not in response.text
    assert _account(db).password_hash not in response.text


def test_the_password_is_stored_only_as_a_hash(client, db, mailer):
    _register(client)

    stored = _account(db).password_hash
    assert stored != PASSWORD
    assert verify_password(PASSWORD, stored)


def test_registering_records_which_notice_was_agreed_and_when(client, db, api_settings, mailer):
    _register(client)

    account = _account(db)
    assert account.consent_version == api_settings.consent_version
    assert account.consent_at is not None


def test_registering_without_agreeing_is_refused(client, db, mailer):
    response = _register(client, accepted_privacy_notice=False)

    assert response.status_code == 400
    assert response.json()["type"] == errors.TYPE_INVALID_REQUEST
    assert _count(db) == 0


def test_nothing_is_sent_when_consent_is_missing(client, mailer):
    _register(client, accepted_privacy_notice=False)

    assert mailer.sent == []


def test_a_password_below_the_minimum_is_refused(client, db, api_settings, mailer):
    response = _register(client, password="x" * (api_settings.minimum_password_length - 1))

    assert response.status_code == 400
    assert str(api_settings.minimum_password_length) in response.json()["detail"]
    assert _count(db) == 0


def test_a_password_at_the_minimum_is_accepted(client, db, api_settings, mailer):
    """The boundary in the other direction, so the comparison cannot drift by one."""
    response = _register(client, password="x" * api_settings.minimum_password_length)

    assert response.status_code == 202
    assert _count(db) == 1


def test_registering_a_taken_address_answers_exactly_as_a_new_one_does(client, db, mailer):
    """Field by field. A difference in any one of them answers the question of who has an
    account here, to anybody willing to ask twice.
    """
    fresh = _register(client, email="new@example.com")
    make_user(db, email=ADDRESS)
    db.commit()

    taken = _register(client)

    assert taken.status_code == fresh.status_code
    assert taken.json() == fresh.json()


def test_registering_a_taken_address_creates_no_second_account(client, db, mailer):
    make_user(db, email=ADDRESS)
    db.commit()

    _register(client)

    assert _count(db) == 1


def test_registering_a_taken_address_leaves_the_existing_one_untouched(client, db, mailer):
    existing = make_user(db, email=ADDRESS, password="the-original-password")
    db.commit()
    before = (existing.password_hash, existing.verified_at, existing.consent_version)

    _register(client)

    db.refresh(existing)
    assert (existing.password_hash, existing.verified_at, existing.consent_version) == before


def test_the_owner_of_a_taken_address_is_told_instead(client, db, mailer):
    """The response cannot say the account exists. The address itself can be told, because
    whoever holds it already knows.
    """
    make_user(db, email=ADDRESS)
    db.commit()

    _register(client)

    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == ADDRESS
    assert "/verify?token=" not in mailer.sent[0].body


def test_an_address_differing_only_in_case_is_the_same_account(client, db, mailer):
    _register(client)

    _register(client, email="Ada@Example.COM")

    assert _count(db) == 1


def test_a_provider_failure_still_leaves_an_account(client, db):
    """A verification message can be requested again; a lost registration cannot be undone."""
    client.app.dependency_overrides[dependencies.mailer_dep] = lambda: RecordingMailer(
        delivers=False
    )

    response = _register(client)

    assert response.status_code == 202
    assert _account(db) is not None


def test_following_the_link_verifies_the_account(client, db, mailer):
    _register(client)

    response = client.post("/api/v1/auth/verify", json={"token": _token_from(mailer)})

    assert response.status_code == 204
    assert _account(db).verified_at is not None


def test_following_the_link_twice_is_refused(client, db, mailer):
    _register(client)
    token = _token_from(mailer)
    client.post("/api/v1/auth/verify", json={"token": token})

    response = client.post("/api/v1/auth/verify", json={"token": token})

    assert response.status_code == 400
    assert response.json()["type"] == errors.TYPE_INVALID_LINK


def test_the_account_stays_verified_after_a_second_attempt(client, db, mailer):
    """The link is single-use. The state it produced is not undone by a second click."""
    _register(client)
    token = _token_from(mailer)
    client.post("/api/v1/auth/verify", json={"token": token})
    verified_at = _account(db).verified_at

    client.post("/api/v1/auth/verify", json={"token": token})

    db.expire_all()
    assert _account(db).verified_at == verified_at


def test_an_unknown_link_is_refused(client, db, mailer):
    response = client.post("/api/v1/auth/verify", json={"token": "not-a-token-anybody-issued"})

    assert response.status_code == 400
    assert response.json()["type"] == errors.TYPE_INVALID_LINK


def test_an_expired_link_is_refused(client, db, mailer):
    _register(client)
    token = _token_from(mailer)
    stored = db.scalar(select(EmailToken).where(EmailToken.token_hash == fingerprint(token)))
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    response = client.post("/api/v1/auth/verify", json={"token": token})

    assert response.status_code == 400
    assert _account(db).verified_at is None


def test_the_refusals_do_not_say_which_one_it_was(client, db, mailer):
    """Unknown, expired and already-spent answer identically. A stranger holding a link
    should not learn from the refusal whether it was ever real.
    """
    _register(client)
    token = _token_from(mailer)
    client.post("/api/v1/auth/verify", json={"token": token})

    spent = client.post("/api/v1/auth/verify", json={"token": token})
    unknown = client.post("/api/v1/auth/verify", json={"token": "never-issued-at-all"})

    assert spent.status_code == unknown.status_code
    assert spent.json() == unknown.json()


def test_the_stored_token_cannot_be_used_to_build_a_working_link(client, db, mailer):
    """What a database dump is worth. The stored value is a digest, and presenting it is
    not presenting the token.
    """
    _register(client)
    stored = db.scalar(select(EmailToken)).token_hash

    assert stored != _token_from(mailer)
    response = client.post("/api/v1/auth/verify", json={"token": stored})

    assert response.status_code == 400
    assert _account(db).verified_at is None


def test_a_second_verification_message_retires_the_first(client, db, mailer):
    """Issuing invalidates what came before, so a link abandoned in an old inbox cannot be
    used later.
    """
    user = make_user(db, email=ADDRESS, verified=False)
    db.commit()
    first = email_tokens.issue(db, user_id=user.id, purpose=email_tokens.VERIFY, lifetime_hours=24)
    second = email_tokens.issue(db, user_id=user.id, purpose=email_tokens.VERIFY, lifetime_hours=24)
    db.commit()

    assert client.post("/api/v1/auth/verify", json={"token": first}).status_code == 400
    assert client.post("/api/v1/auth/verify", json={"token": second}).status_code == 204
