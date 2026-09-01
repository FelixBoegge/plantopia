"""Deleting your own account, over the wire.

The service's own tests prove what a deletion reaches. These prove the endpoint cannot be
pointed at anybody else, and that both halves of the confirmation are enforced here rather
than only in a browser.
"""

import pytest
from sqlalchemy import func, select

from data.models import Base, User
from services.erasure import CONFIRMATION

PASSWORD = "a-long-enough-password"


@pytest.fixture
def owner_password(db, owner) -> str:
    """Give the signed-in owner a password they can actually re-enter.

    The shared `owner` fixture is created with the unusable sentinel — most tests only need
    somebody to scope records to, and a working login by default would be a login nobody
    asked for. Deletion is the one endpoint that needs the real thing.
    """
    from identity.passwords import hash_password

    db.get(User, owner).password_hash = hash_password(PASSWORD)
    db.flush()
    return PASSWORD


@pytest.fixture
def unauthenticated_client(client):
    client.headers.pop("Authorization", None)
    return client


@pytest.fixture(autouse=True)
def _no_checkpoints(monkeypatch):
    """The checkpoint sweep runs against the checkpointer's own pool, outside this test's
    transaction. Its behaviour is covered by `tests/unit/agent/test_checkpoints.py`."""
    from services import erasure

    monkeypatch.setattr(erasure.checkpoints, "delete_for_user", lambda url, user_id: 0)


def _count(session, table: str) -> int:
    return session.scalar(select(func.count()).select_from(Base.metadata.tables[table]))


class TestDeletingYourOwnAccount:
    def test_it_takes_no_identifier(self):
        """The only account this can delete is the one the request is authenticated as.

        An endpoint that accepted an identifier would be one that could be pointed at
        somebody else, defended only by a check somebody has to remember to write.
        """
        from api.routers.account import delete_me

        parameters = set(delete_me.__annotations__) - {"return"}

        assert parameters == {"body", "session", "owner", "settings"}
        from api.schemas import DeleteAccountIn

        assert set(DeleteAccountIn.model_fields) == {"password", "confirmation"}

    def test_a_confirmed_deletion_succeeds(self, client, db, owner_password):
        response = client.request(
            "DELETE",
            "/api/v1/me",
            json={"password": owner_password, "confirmation": CONFIRMATION},
        )

        assert response.status_code == 204
        assert response.content == b""

    def test_the_account_and_its_records_are_gone(self, client, db, owner_password, seeded):
        client.request(
            "DELETE",
            "/api/v1/me",
            json={"password": owner_password, "confirmation": CONFIRMATION},
        )

        assert _count(db, "users") == 0
        assert _count(db, "plants") == 0
        assert _count(db, "diagnoses") == 0


class TestWhatItRefuses:
    def test_the_wrong_password(self, client, db, owner_password):
        response = client.request(
            "DELETE",
            "/api/v1/me",
            json={"password": "not-the-password", "confirmation": CONFIRMATION},
        )

        assert response.status_code == 400
        assert _count(db, "users") == 1

    def test_a_missing_password(self, client, db):
        response = client.request("DELETE", "/api/v1/me", json={"confirmation": CONFIRMATION})

        assert response.status_code == 422
        assert _count(db, "users") == 1

    def test_the_confirmation_not_typed(self, client, db, owner_password):
        """The right password and no confirmation deletes nothing. This is the half a
        client could otherwise enforce alone — and a script would not have to type."""
        response = client.request(
            "DELETE", "/api/v1/me", json={"password": owner_password, "confirmation": "yes"}
        )

        assert response.status_code == 400
        assert _count(db, "users") == 1

    def test_a_missing_confirmation(self, client, db, owner_password):
        response = client.request("DELETE", "/api/v1/me", json={"password": owner_password})

        assert response.status_code == 422
        assert _count(db, "users") == 1

    def test_the_refusal_says_which_half_was_wrong(self, client, owner_password):
        """Unlike a sign-in. The caller is already authenticated as this account, so saying
        the password was mistyped reveals nothing the session does not already establish —
        and being vague would leave somebody retrying a correct password forever."""
        wrong_password = client.request(
            "DELETE",
            "/api/v1/me",
            json={"password": "nope", "confirmation": CONFIRMATION},
        ).json()
        wrong_phrase = client.request(
            "DELETE", "/api/v1/me", json={"password": owner_password, "confirmation": "nope"}
        ).json()

        assert wrong_password["detail"] != wrong_phrase["detail"]

    def test_signed_out(self, unauthenticated_client, db):
        response = unauthenticated_client.request(
            "DELETE", "/api/v1/me", json={"password": "x", "confirmation": CONFIRMATION}
        )

        assert response.status_code == 401
        assert _count(db, "users") >= 1


class TestTheConfirmationPhrase:
    @pytest.mark.parametrize("typed", [CONFIRMATION, CONFIRMATION.upper(), f"  {CONFIRMATION}  "])
    def test_case_and_spacing_are_forgiven(self, client, owner_password, typed):
        """Somebody who typed the words meant them. Refusing over a capital letter would be
        pedantry standing between a person and a thing they asked for twice."""
        response = client.request(
            "DELETE", "/api/v1/me", json={"password": owner_password, "confirmation": typed}
        )

        assert response.status_code == 204

    @pytest.mark.parametrize("typed", ["delete", "delete my", "delete my accounts", "yes"])
    def test_something_else_is_not_forgiven(self, client, db, owner_password, typed):
        response = client.request(
            "DELETE", "/api/v1/me", json={"password": owner_password, "confirmation": typed}
        )

        assert response.status_code == 400
        assert _count(db, "users") == 1


class TestAfterwards:
    def test_a_refresh_is_refused(self, client, db, owner_password):
        """The sessions are revoked, so the one thing an outstanding access token could do
        to outlive its fifteen minutes — trade itself for a new one — is closed."""
        client.request(
            "DELETE",
            "/api/v1/me",
            json={"password": owner_password, "confirmation": CONFIRMATION},
        )

        assert client.post("/api/v1/auth/refresh").status_code == 401

    def test_a_read_with_the_old_access_token_finds_nothing(self, client, db, owner_password):
        """`api/dependencies.current_owner` believes a token on its signature alone and
        reads no row — the deal a stateless token makes. So the token still parses, and
        there is simply nothing of that owner's left to return."""
        client.request(
            "DELETE",
            "/api/v1/me",
            json={"password": owner_password, "confirmation": CONFIRMATION},
        )

        assert client.get("/api/v1/plants").json() == []
