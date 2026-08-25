"""Sessions, rotation, and what happens when a token is used twice.

The reuse behaviour is the part most likely to be wrong and most costly if it is, so it is
asserted directly rather than inferred from a sign-in that happens to work.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from core.config import Settings
from data.models import RefreshToken
from identity import sessions
from identity.sessions import InvalidRefreshTokenError, RefreshTokenReusedError
from identity.tokens import fingerprint, read_access_token
from tests.people import make_user
from tests.secrets import TEST_JWT_SECRET


@pytest.fixture
def settings():
    return Settings(_env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET)


@pytest.fixture
def person(db):
    return make_user(db).id


def test_signing_in_issues_both_tokens(db, person, settings):
    issued = sessions.start(db, user_id=person, settings=settings)

    assert read_access_token(issued.access_token, secret=settings.jwt_secret) == person
    assert issued.refresh_token


def test_the_refresh_token_is_stored_only_as_a_hash(db, person, settings):
    """A database dump must not be a set of working sessions."""
    issued = sessions.start(db, user_id=person, settings=settings)

    stored = db.scalar(select(RefreshToken).where(RefreshToken.user_id == person))
    assert stored.token_hash != issued.refresh_token
    assert stored.token_hash == fingerprint(issued.refresh_token)


def test_refreshing_issues_a_new_pair(db, person, settings):
    first = sessions.start(db, user_id=person, settings=settings)

    second = sessions.refresh(db, presented=first.refresh_token, settings=settings)

    assert second.refresh_token != first.refresh_token
    assert read_access_token(second.access_token, secret=settings.jwt_secret) == person


def test_refreshing_stays_in_the_same_family(db, person, settings):
    first = sessions.start(db, user_id=person, settings=settings)

    second = sessions.refresh(db, presented=first.refresh_token, settings=settings)

    assert second.family_id == first.family_id


def test_the_presented_token_stops_working(db, person, settings):
    first = sessions.start(db, user_id=person, settings=settings)
    sessions.refresh(db, presented=first.refresh_token, settings=settings)

    with pytest.raises(RefreshTokenReusedError):
        sessions.refresh(db, presented=first.refresh_token, settings=settings)


def test_reuse_invalidates_the_whole_family(db, person, settings):
    """Refusing only the reused token would leave the newer one working — and the newer
    one is the thief's if the thief refreshed first."""
    first = sessions.start(db, user_id=person, settings=settings)
    second = sessions.refresh(db, presented=first.refresh_token, settings=settings)

    with pytest.raises(RefreshTokenReusedError):
        sessions.refresh(db, presented=first.refresh_token, settings=settings)

    with pytest.raises(InvalidRefreshTokenError):
        sessions.refresh(db, presented=second.refresh_token, settings=settings)


def test_a_second_device_survives_the_first_being_compromised(db, person, settings):
    """Families are per sign-in, so one device's session ending is not everybody's."""
    laptop = sessions.start(db, user_id=person, settings=settings)
    phone = sessions.start(db, user_id=person, settings=settings)
    sessions.refresh(db, presented=laptop.refresh_token, settings=settings)

    with pytest.raises(RefreshTokenReusedError):
        sessions.refresh(db, presented=laptop.refresh_token, settings=settings)

    still_working = sessions.refresh(db, presented=phone.refresh_token, settings=settings)
    assert still_working.family_id == phone.family_id


def test_an_unknown_token_is_refused(db, settings):
    with pytest.raises(InvalidRefreshTokenError):
        sessions.refresh(db, presented="not a token anybody issued", settings=settings)


def test_an_expired_token_is_refused(db, person, settings):
    issued = sessions.start(db, user_id=person, settings=settings)
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == fingerprint(issued.refresh_token))
    )
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    with pytest.raises(InvalidRefreshTokenError):
        sessions.refresh(db, presented=issued.refresh_token, settings=settings)


def test_signing_out_ends_the_session(db, person, settings):
    issued = sessions.start(db, user_id=person, settings=settings)

    sessions.end(db, presented=issued.refresh_token)

    with pytest.raises(InvalidRefreshTokenError):
        sessions.refresh(db, presented=issued.refresh_token, settings=settings)


def test_signing_out_ends_the_family_not_just_the_token(db, person, settings):
    """Every token that device could still rotate into belongs to the same family."""
    first = sessions.start(db, user_id=person, settings=settings)
    second = sessions.refresh(db, presented=first.refresh_token, settings=settings)

    sessions.end(db, presented=second.refresh_token)

    with pytest.raises(InvalidRefreshTokenError):
        sessions.refresh(db, presented=second.refresh_token, settings=settings)


def test_signing_out_with_an_unknown_token_is_silent(db):
    """Signing out is a request to be signed out. Reporting that a token was already
    invalid tells an unauthenticated caller which tokens exist."""
    sessions.end(db, presented="never issued")  # must not raise


def test_ending_every_session_leaves_none_working(db, person, settings):
    """What a password reset does: somebody resetting a password they may not have chosen
    to forget should not leave the reason for the reset signed in."""
    laptop = sessions.start(db, user_id=person, settings=settings)
    phone = sessions.start(db, user_id=person, settings=settings)

    ended = sessions.revoke_all_for_user(db, person)

    assert ended == 2
    for token in (laptop, phone):
        with pytest.raises(InvalidRefreshTokenError):
            sessions.refresh(db, presented=token.refresh_token, settings=settings)


def test_ending_one_persons_sessions_leaves_another_alone(db, person, settings):
    mine = sessions.start(db, user_id=person, settings=settings)
    other = make_user(db)
    theirs = sessions.start(db, user_id=other.id, settings=settings)

    sessions.revoke_all_for_user(db, person)

    assert sessions.refresh(db, presented=theirs.refresh_token, settings=settings)
    with pytest.raises(InvalidRefreshTokenError):
        sessions.refresh(db, presented=mine.refresh_token, settings=settings)


def test_rotation_does_not_accumulate_live_tokens(db, person, settings):
    """Each refresh retires the token it replaces, so a long-lived session leaves a trail
    of retired rows rather than a pile of working ones."""
    issued = sessions.start(db, user_id=person, settings=settings)
    for _ in range(5):
        issued = sessions.refresh(db, presented=issued.refresh_token, settings=settings)

    live = db.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(
            RefreshToken.user_id == person,
            RefreshToken.used_at.is_(None),
            RefreshToken.revoked_at.is_(None),
        )
    )
    assert live == 1
