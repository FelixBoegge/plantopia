"""What graph state costs to persist.

`M15` measured the arrangement this replaces: two completed diagnoses of 3 MB
photographs produced **205 MB** of checkpoint blobs against a 69 KB main database,
because `ImageRef` carried base64 and LangGraph re-serialises the whole state at every
superstep. Nothing noticed until the code tour, since no test used a realistic image
and the main database looked tiny.

So this file uses a realistic image and asserts on the size.
"""

import json

import pytest

from agent.state import DiagnosisState, ImageRef
from core.blobs import PostgresBlobStore

# Four megabytes, the size of an ordinary phone photograph and roughly what M15 was
# measured against.
BIG_IMAGE = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"x" * (4 * 1024 * 1024)


@pytest.fixture
def stored_images(db, owner):
    store = PostgresBlobStore(db)
    return [
        ImageRef(ref=store.put(owner, BIG_IMAGE, "image/png"), media_type="image/png")
        for _ in range(4)
    ]


def _serialised(state: DiagnosisState) -> bytes:
    """What the checkpointer writes, near enough: the state as JSON."""
    return json.dumps(state.model_dump(mode="json")).encode()


# A ceiling on an empty state referencing four photographs.
#
# **Raised deliberately, and rarely.** It was 1024 and was tripped honestly on 2026-08-31 by
# four scalar fields two changes had added — a capture date, a coarse position, a detected
# place name. Fifteen bytes over, all of them nulls. Raising a threshold because it failed is
# how a guard dies, so the number moved once, with a note, and the *property* that actually
# guards M15 is asserted separately below: a state must not grow with the photographs it
# references. That one cannot be satisfied by editing a constant.
MAX_STATE_BYTES = 2048


def test_state_holding_four_photographs_stays_small(stored_images):
    """Sixteen megabytes of photographs, and the state that references them is a couple of
    kilobytes — which is the whole point of carrying keys."""
    state = DiagnosisState(images=stored_images, plant_name="Basil", location_kind="indoor")

    assert len(_serialised(state)) < MAX_STATE_BYTES


def test_the_state_is_negligible_beside_the_photographs(stored_images):
    """The bound that does not need maintaining. Sixteen megabytes of photographs against a
    state that references them: any arrangement carrying pixels fails this by five orders of
    magnitude, whatever the constant above happens to be."""
    state = DiagnosisState(images=stored_images, plant_name="Basil", location_kind="indoor")

    assert len(_serialised(state)) < len(BIG_IMAGE) / 1000


def test_no_image_bytes_appear_in_serialised_state(stored_images):
    """Asserted on content as well as size, so a future field that smuggles pixels in
    under a different name fails here rather than in a disk-usage report."""
    state = DiagnosisState(images=stored_images, plant_name="Basil", location_kind="indoor")

    assert b"x" * 1000 not in _serialised(state)


def test_state_size_does_not_grow_with_photograph_size(db, owner):
    """The property that matters: a bigger photograph must not make a bigger checkpoint.
    Under the previous arrangement this test would fail by roughly the file size."""
    store = PostgresBlobStore(db)
    small = ImageRef(ref=store.put(owner, b"tiny", "image/png"), media_type="image/png")
    large = ImageRef(ref=store.put(owner, BIG_IMAGE, "image/png"), media_type="image/png")

    with_small = DiagnosisState(images=[small], plant_name="B", location_kind="indoor")
    with_large = DiagnosisState(images=[large], plant_name="B", location_kind="indoor")

    assert len(_serialised(with_small)) == len(_serialised(with_large))
