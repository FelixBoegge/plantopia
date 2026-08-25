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
    recheck_thread,
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


def test_a_recheck_handle_is_stable_for_the_same_attempt():
    """Derived rather than random, so returning to a re-check resumes it instead of
    starting a second paid run."""
    owner, plant, diagnosis = new_id(), new_id(), new_id()

    assert recheck_thread(owner, plant, diagnosis, 0) == recheck_thread(owner, plant, diagnosis, 0)


def test_a_new_attempt_gets_a_new_recheck_handle():
    """U7: neither a rejection nor a retake writes a diagnosis, so without the attempt
    counter the derived handle would not move and the retry would resume the wreckage of
    the attempt that was abandoned."""
    owner, plant, diagnosis = new_id(), new_id(), new_id()

    assert recheck_thread(owner, plant, diagnosis, 0) != recheck_thread(owner, plant, diagnosis, 1)


def test_a_recheck_before_any_diagnosis_still_has_a_handle():
    owner, plant = new_id(), new_id()

    assert owner_of(recheck_thread(owner, plant, None, 0)) == owner


def test_chat_and_diagnosis_handles_for_one_plant_are_distinct():
    """Sharing a checkpointer is only safe because the two cannot collide."""
    owner, plant = new_id(), new_id()

    assert chat_thread(owner, plant) != recheck_thread(owner, plant, None, 0)


def test_a_handle_cannot_be_built_from_another_owners_data():
    """The old scheme was recheck-{plant_id}-{diagnosis_id}-{attempt} — three values a
    second user could plausibly obtain or enumerate. Knowing them is no longer enough."""
    theirs, mine = new_id(), new_id()
    plant, diagnosis = new_id(), new_id()

    guessed = recheck_thread(mine, plant, diagnosis, 0)

    assert guessed != recheck_thread(theirs, plant, diagnosis, 0)
    with pytest.raises(ThreadOwnershipError):
        verify_owner(guessed, theirs)


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
    assert recheck_thread(owner, new_id(), None, 0).startswith(prefix)


def test_one_owners_prefix_does_not_match_another():
    first, second = new_id(), new_id()

    assert not diagnosis_thread(second).startswith(prefix_for(first))
