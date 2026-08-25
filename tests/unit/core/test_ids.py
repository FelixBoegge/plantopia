"""Identifiers must be unique, and must sort in the order they were made."""

from core.ids import new_id


def test_identifiers_are_distinct():
    assert len({new_id() for _ in range(100)}) == 100


def test_identifiers_sort_in_generation_order():
    """The ordering is the reason for choosing v7 over v4, so it is worth asserting
    rather than trusting: a v4 generator would pass the uniqueness test above and fail
    this one roughly always."""
    made = [new_id() for _ in range(100)]

    assert sorted(made) == made


def test_identifiers_declare_version_seven():
    """A v4 would satisfy both tests above on a fast enough machine if the timestamp
    never advanced, so pin the version itself."""
    assert new_id().version == 7
