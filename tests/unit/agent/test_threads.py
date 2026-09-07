"""Thread handles: who they name, and who may use them.

A handle resumes a paused diagnosis — one that has already spent money and is holding
someone's photographs. These tests are about the property that matters: the handle is
not guessable from another owner's data, and presenting somebody else's is refused.
"""

import pytest

from agent.threads import (
    ThreadOwnershipError,
    chat_thread,
    diagnosis_thread,
    owner_of,
    prefix_for,
    verify_owner,
)
from core.ids import new_id


def test_a_diagnosis_handle_names_its_owner():
    owner = new_id()

    assert owner_of(diagnosis_thread(owner)) == owner


def test_two_diagnoses_for_one_owner_get_different_handles():
    """The wizard has no plant yet when it starts, so there is nothing stable to name a
    first diagnosis by — and two concurrent uploads must not collide."""
    owner = new_id()

    assert diagnosis_thread(owner) != diagnosis_thread(owner)


def test_the_owner_may_use_their_own_handle():
    owner = new_id()

    verify_owner(diagnosis_thread(owner), owner)  # must not raise


@pytest.mark.parametrize(
    "handle", ["", "nonsense", "recheck-3-4-0", "not-a-uuid:diagnose:abc", ":diagnose:abc"]
)
def test_an_unrecognisable_handle_belongs_to_nobody(handle):
    """Including the old scheme's format, which must not resolve to an owner now."""
    assert owner_of(handle) is None

    with pytest.raises(ThreadOwnershipError):
        verify_owner(handle, new_id())


def test_every_handle_for_one_owner_shares_a_prefix():
    """Which is what makes an owner's run state deletable: nothing else relates a
    checkpoint row to a person."""
    owner = new_id()
    prefix = prefix_for(owner)

    assert diagnosis_thread(owner).startswith(prefix)
    assert chat_thread(owner, new_id()).startswith(prefix)


def test_one_owners_prefix_does_not_match_another():
    first, second = new_id(), new_id()

    assert not diagnosis_thread(second).startswith(prefix_for(first))
