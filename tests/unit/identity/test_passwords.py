"""Password hashing."""

from identity.passwords import UNUSABLE, hash_password, needs_rehash, verify

PASSWORD = "correct horse battery staple"


def test_a_hash_is_not_the_password():
    stored = hash_password(PASSWORD)

    assert stored != PASSWORD
    assert PASSWORD not in stored


def test_the_right_password_verifies():
    assert verify(PASSWORD, hash_password(PASSWORD))


def test_a_wrong_password_does_not():
    assert not verify("something else", hash_password(PASSWORD))


def test_two_accounts_with_the_same_password_store_different_values():
    """Salted per call, so a stolen database does not reveal which accounts share a
    password — which is the fact that makes one cracked password worth many."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_it_is_argon2id():
    assert hash_password(PASSWORD).startswith("$argon2id$")


def test_an_unusable_hash_verifies_against_nothing():
    """The seeded owner predates accounts and must never become one. Nothing signs in as
    it, whatever is presented."""
    assert not verify("", UNUSABLE)
    assert not verify(PASSWORD, UNUSABLE)


def test_a_malformed_hash_is_refused_rather_than_raising():
    """The caller is a sign-in path. "Wrong password" and "this row cannot be signed in
    to" must not be distinguishable by an unauthenticated caller — including by one
    causing a 500 rather than a 401."""
    assert not verify(PASSWORD, "not a hash at all")
    assert not verify(PASSWORD, "")


def test_a_current_hash_does_not_need_rehashing():
    assert not needs_rehash(hash_password(PASSWORD))


def test_a_malformed_hash_does_not_ask_to_be_rehashed():
    assert not needs_rehash("not a hash")
