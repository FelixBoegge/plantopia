"""The blob store: opaque keys, owner-scoped reads, complete removal."""

from datetime import UTC, datetime

from core.blobs import PostgresBlobStore
from core.ids import new_id
from data.models import User

PNG = b"\x89PNG\r\n\x1a\n" + b"pretend pixels" * 100


def _owner(session):
    user = User(email=f"{new_id()}@example.test", created_at=datetime.now(UTC))
    session.add(user)
    session.flush()
    return user.id


def test_bytes_round_trip_under_the_key_they_were_stored_with(pg_session):
    store = PostgresBlobStore(pg_session)
    owner = _owner(pg_session)

    key = store.put(owner, PNG, "image/png")

    assert store.get(owner, key) == PNG


def test_the_key_exists_before_the_flush_completes(pg_session):
    """The key is the return value, so it cannot wait for a database-assigned default —
    ``store_upload`` needs it to build the ImageRef it hands back."""
    store = PostgresBlobStore(pg_session)
    owner = _owner(pg_session)

    key = store.put(owner, PNG, "image/png")

    assert key is not None
    assert key.version == 7


def test_an_unknown_key_returns_nothing(pg_session):
    store = PostgresBlobStore(pg_session)

    assert store.get(_owner(pg_session), new_id()) is None


def test_another_owners_key_is_indistinguishable_from_an_unknown_one(pg_session):
    """Separating the two would confirm that somebody else's photograph exists."""
    store = PostgresBlobStore(pg_session)
    first, second = _owner(pg_session), _owner(pg_session)
    key = store.put(first, PNG, "image/png")

    assert store.get(second, key) is None
    assert store.get(second, new_id()) is None


def test_removing_an_owners_photographs_leaves_other_owners_alone(pg_session):
    store = PostgresBlobStore(pg_session)
    first, second = _owner(pg_session), _owner(pg_session)
    mine = store.put(first, PNG, "image/png")
    theirs = store.put(second, PNG, "image/png")

    removed = store.delete_for_user(first)
    pg_session.flush()

    assert removed == 1
    assert store.get(first, mine) is None
    assert store.get(second, theirs) == PNG


def test_the_stored_size_matches_what_was_written(pg_session):
    """Recorded on the row so a storage report never has to read the bytes back."""
    from data.models import Blob

    store = PostgresBlobStore(pg_session)
    owner = _owner(pg_session)
    key = store.put(owner, PNG, "image/png")

    assert pg_session.get(Blob, key).byte_size == len(PNG)
