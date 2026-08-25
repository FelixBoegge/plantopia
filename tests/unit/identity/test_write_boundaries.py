"""Every identity operation that writes, commits.

This exists because ``register`` once did not. It flushed and returned, so the account was
visible to the rest of the request, the verification email went out, and the row was
discarded when the session closed. Registration failed completely and silently, and
returned 202.

Nothing else in the suite could see it. Tests run inside a transaction that is rolled back,
where a flush and a commit look identical — which is what makes them fast and isolated, and
what makes this particular defect invisible to every other test in the file next door.

So the assertion here is not about data. It is that the operation *commits*: that it owns
its write boundary rather than leaving it to a caller who, in production, is a request
handler that only closes the session.
"""

import pytest
from sqlalchemy.orm import Session

from core.config import Settings
from core.mail import Message
from identity import accounts, email_tokens, sessions
from tests.people import make_user
from tests.secrets import TEST_JWT_SECRET

PASSWORD = "a-long-enough-password"


class _SilentMailer:
    def send(self, message: Message) -> bool:
        return True


@pytest.fixture
def settings():
    return Settings(_env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET)


@pytest.fixture
def commits(monkeypatch):
    """Counts commits on the session, without changing what one does."""
    counter = {"n": 0}
    original = Session.commit

    def _counting(self, *args, **kwargs):
        counter["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Session, "commit", _counting)
    return counter


def test_registering_commits(db, settings, commits):
    """The one this file was written for."""
    accounts.register(
        db,
        email="new@example.com",
        password=PASSWORD,
        consented=True,
        settings=settings,
        mailer=_SilentMailer(),
    )

    assert commits["n"] > 0


def test_verifying_commits(db, settings, commits):
    user = make_user(db, verified=False)
    token = email_tokens.issue(db, user_id=user.id, purpose=email_tokens.VERIFY, lifetime_hours=24)
    db.commit()
    commits["n"] = 0

    accounts.verify(db, presented=token)

    assert commits["n"] > 0


def test_signing_in_commits_the_session_it_issued(db, settings, commits):
    user = make_user(db, password=PASSWORD, verified=True)
    db.commit()
    commits["n"] = 0

    sessions.start(db, user_id=user.id, settings=settings)

    assert commits["n"] > 0


def test_refreshing_commits(db, settings, commits):
    user = make_user(db, password=PASSWORD, verified=True)
    issued = sessions.start(db, user_id=user.id, settings=settings)
    commits["n"] = 0

    sessions.refresh(db, presented=issued.refresh_token, settings=settings)

    assert commits["n"] > 0


def test_reuse_detection_commits_before_it_refuses(db, settings, commits):
    """The revocation has to outlive the refusal. Rolled back with it, the thief's newer
    token keeps working — which is the entire failure this mechanism prevents.
    """
    user = make_user(db, password=PASSWORD, verified=True)
    issued = sessions.start(db, user_id=user.id, settings=settings)
    sessions.refresh(db, presented=issued.refresh_token, settings=settings)
    commits["n"] = 0

    with pytest.raises(sessions.RefreshTokenReusedError):
        sessions.refresh(db, presented=issued.refresh_token, settings=settings)

    assert commits["n"] > 0


def test_signing_out_commits(db, settings, commits):
    user = make_user(db, password=PASSWORD, verified=True)
    issued = sessions.start(db, user_id=user.id, settings=settings)
    commits["n"] = 0

    sessions.end(db, presented=issued.refresh_token)

    assert commits["n"] > 0


def test_requesting_a_reset_commits(db, settings, commits):
    user = make_user(db, password=PASSWORD, verified=True)
    db.commit()
    commits["n"] = 0

    accounts.request_reset(db, email=user.email, settings=settings, mailer=_SilentMailer())

    assert commits["n"] > 0


def test_resetting_a_password_commits(db, settings, commits):
    user = make_user(db, password=PASSWORD, verified=True)
    token = email_tokens.issue(db, user_id=user.id, purpose=email_tokens.RESET, lifetime_hours=1)
    db.commit()
    commits["n"] = 0

    accounts.reset_password(
        db, presented=token, password="a-brand-new-long-password", settings=settings
    )

    assert commits["n"] > 0


def test_a_refused_registration_commits_nothing(db, settings, commits):
    """The other direction: a refusal that opened and rolled back a write transaction would
    let an unauthenticated caller make the database work for nothing.
    """
    with pytest.raises(accounts.ConsentRequiredError):
        accounts.register(
            db,
            email="new@example.com",
            password=PASSWORD,
            consented=False,
            settings=settings,
            mailer=_SilentMailer(),
        )

    assert commits["n"] == 0


def test_a_refused_verification_commits_nothing(db, settings, commits):
    with pytest.raises(accounts.VerificationError):
        accounts.verify(db, presented="never-issued")

    assert commits["n"] == 0


def test_a_registration_that_finds_the_address_taken_commits_nothing(db, settings, commits):
    user = make_user(db, verified=True)
    db.commit()
    commits["n"] = 0

    accounts.register(
        db,
        email=user.email,
        password=PASSWORD,
        consented=True,
        settings=settings,
        mailer=_SilentMailer(),
    )

    assert commits["n"] == 0


def test_a_reset_for_an_unknown_address_commits_nothing(db, settings, commits):
    accounts.request_reset(
        db, email="nobody@example.com", settings=settings, mailer=_SilentMailer()
    )

    assert commits["n"] == 0


def test_the_counter_would_notice_a_missing_commit(db, settings, commits):
    """Guards the guard: a counter that never increments would pass every test above."""
    make_user(db)
    db.flush()

    assert commits["n"] == 0

    db.commit()

    assert commits["n"] == 1
