"""Tokens, tested before anything routes to them.

These are the pieces where a mistake is a security defect rather than a bug, so each
property is asserted directly rather than inferred from a passing sign-in.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from core.ids import new_id
from identity.tokens import (
    ALGORITHM,
    TokenExpiredError,
    TokenInvalidError,
    expires_in,
    fingerprint,
    has_expired,
    issue_access_token,
    matches,
    new_secret_token,
    read_access_token,
)

SECRET = "a-secret-for-tests-long-enough-for-hmac-sha256"


class TestAccessTokens:
    def test_a_token_resolves_to_the_person_it_was_issued_for(self):
        owner = new_id()

        token = issue_access_token(user_id=owner, secret=SECRET, lifetime_minutes=15)

        assert read_access_token(token, secret=SECRET) == owner

    def test_an_expired_token_is_refused_as_expired(self):
        """Distinct from invalid, so a client knows to refresh rather than sign in again."""
        owner = new_id()
        token = issue_access_token(user_id=owner, secret=SECRET, lifetime_minutes=-1)

        with pytest.raises(TokenExpiredError):
            read_access_token(token, secret=SECRET)

    def test_a_token_signed_with_another_secret_is_refused(self):
        token = issue_access_token(
            user_id=new_id(),
            secret="somebody-elses-secret-also-long-enough-here",
            lifetime_minutes=15,
        )

        with pytest.raises(TokenInvalidError):
            read_access_token(token, secret=SECRET)

    def test_a_tampered_token_is_refused(self):
        token = issue_access_token(user_id=new_id(), secret=SECRET, lifetime_minutes=15)
        header, payload, signature = token.split(".")
        forged = f"{header}.{payload}x.{signature}"

        with pytest.raises(TokenInvalidError):
            read_access_token(forged, secret=SECRET)

    def test_an_unsigned_token_is_refused(self):
        """`alg: none` is how a forged token gets believed by a decoder that trusts the
        token's own header. The algorithm is pinned at the call site."""
        owner = new_id()
        unsigned = jwt.encode(
            {"sub": str(owner), "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())},
            key="",
            algorithm="none",
        )

        with pytest.raises(TokenInvalidError):
            read_access_token(unsigned, secret=SECRET)

    def test_a_token_naming_no_owner_is_refused(self):
        token = jwt.encode(
            {
                "sub": "not-an-identifier",
                "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
            },
            SECRET,
            algorithm=ALGORITHM,
        )

        with pytest.raises(TokenInvalidError):
            read_access_token(token, secret=SECRET)

    def test_nonsense_is_refused(self):
        with pytest.raises(TokenInvalidError):
            read_access_token("not a token at all", secret=SECRET)

    def test_two_tokens_for_one_person_differ(self):
        """Each carries its own identifier, so a future denylist has something to key on."""
        owner = new_id()

        first = issue_access_token(user_id=owner, secret=SECRET, lifetime_minutes=15)
        second = issue_access_token(user_id=owner, secret=SECRET, lifetime_minutes=15)

        assert first != second


class TestSecretTokens:
    def test_two_tokens_are_never_the_same(self):
        assert len({new_secret_token() for _ in range(500)}) == 500

    def test_the_stored_form_is_not_the_token(self):
        """A database dump must not be a set of working sessions and reset links."""
        token = new_secret_token()

        assert fingerprint(token) != token
        assert token not in fingerprint(token)

    def test_a_token_matches_its_own_fingerprint(self):
        token = new_secret_token()

        assert matches(token, fingerprint(token))

    def test_a_different_token_does_not_match(self):
        assert not matches(new_secret_token(), fingerprint(new_secret_token()))

    def test_the_fingerprint_is_stable(self):
        token = new_secret_token()

        assert fingerprint(token) == fingerprint(token)


class TestExpiry:
    def test_a_future_expiry_has_not_passed(self):
        assert not has_expired(expires_in(hours=1))

    def test_a_past_expiry_has_passed(self):
        assert has_expired(datetime.now(UTC) - timedelta(seconds=1))

    def test_an_expiry_exactly_now_has_passed(self):
        """The boundary belongs to expired: a token valid at the instant it expires is a
        token whose lifetime is off by one moment in the direction that favours a thief."""
        moment = datetime.now(UTC)

        assert has_expired(moment, now=moment)

    def test_a_naive_timestamp_is_read_as_utc(self):
        """Everything stored is timezone-aware; a value that lost its offset in transit
        must not silently compare as being in the future."""
        past = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)

        assert has_expired(past)
