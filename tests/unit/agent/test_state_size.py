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


def test_state_holding_four_photographs_stays_small(stored_images):
    """Sixteen megabytes of photographs, and the state that references them is under a
    kilobyte — which is the whole point of carrying keys."""
    state = DiagnosisState(images=stored_images, plant_name="Basil", location_kind="indoor")

    assert len(_serialised(state)) < 1024


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
