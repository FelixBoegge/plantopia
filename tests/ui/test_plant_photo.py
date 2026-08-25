"""Tests for the My Plants card photograph.

Photographs come from the blob store now rather than from a directory of files, so
resolution is a key lookup and the fallbacks are about keys rather than about missing
files. The cropping tests are unchanged in substance: what they assert is that every
orientation ends at one aspect ratio, which is what keeps cards the same height.
"""

from io import BytesIO
from uuid import UUID

import pytest
from PIL import Image

from core.ids import new_id
from ui.components.plant_photo import _ASPECT

pytestmark = pytest.mark.ui

OWNER = new_id()


def _png(size) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (10, 120, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeBlobs:
    """A blob store in a dict, owner-scoped like the real one."""

    def __init__(self) -> None:
        self._data: dict[tuple, bytes] = {}

    def put(self, user_id, data: bytes, content_type: str) -> UUID:
        key = new_id()
        self._data[(user_id, key)] = data
        return key

    def get(self, user_id, key):
        return self._data.get((user_id, key))

    def delete_for_user(self, user_id) -> int:
        keys = [k for k in self._data if k[0] == user_id]
        for k in keys:
            del self._data[k]
        return len(keys)


@pytest.fixture
def blobs():
    return FakeBlobs()


def test_a_missing_reference_resolves_to_nothing(blobs):
    from ui.components.plant_photo import resolve_photo

    assert resolve_photo(None, blobs, OWNER) is None


def test_a_stored_photograph_resolves_to_its_bytes(blobs):
    from ui.components.plant_photo import resolve_photo

    data = _png((40, 30))
    key = blobs.put(OWNER, data, "image/png")

    assert resolve_photo(str(key), blobs, OWNER) == data


def test_a_reference_to_nothing_resolves_to_nothing(blobs):
    """A plant whose photograph has been deleted still renders — as a placeholder."""
    from ui.components.plant_photo import resolve_photo

    assert resolve_photo(str(new_id()), blobs, OWNER) is None


def test_another_owners_photograph_resolves_to_nothing(blobs):
    """The store is owner-scoped, so a key from elsewhere is indistinguishable from one
    that never existed — which is what stops a card leaking somebody else's plant."""
    from ui.components.plant_photo import resolve_photo

    key = blobs.put(OWNER, _png((40, 30)), "image/png")

    assert resolve_photo(str(key), blobs, new_id()) is None


def test_a_reference_that_is_not_a_key_resolves_to_nothing(blobs):
    """A photo_ref written before photographs moved into the store. Not an error; there
    is simply nothing behind it any more."""
    from ui.components.plant_photo import resolve_photo

    assert resolve_photo("abc123", blobs, OWNER) is None


@pytest.mark.parametrize(
    "size", [(1200, 1600), (1600, 1200), (800, 800)], ids=["portrait", "landscape", "square"]
)
def test_every_orientation_crops_to_one_aspect_ratio(size):
    """The point of cropping: equal-width columns then give equal image heights, so a
    portrait phone photo cannot make its card twice as tall as its neighbours."""
    from ui.components.plant_photo import _banner_bytes

    with Image.open(BytesIO(_banner_bytes.__wrapped__("ref", _png(size)))) as banner:
        assert banner.width / banner.height == pytest.approx(_ASPECT, abs=0.01)


def test_a_corrupt_upload_falls_back_instead_of_raising(blobs):
    """A bad image should cost the owner a thumbnail, not the whole plant grid."""
    from ui.components.plant_photo import render_plant_photo

    key = blobs.put(OWNER, b"not an image at all", "image/png")

    render_plant_photo(str(key), blobs, OWNER)  # must not raise


def test_a_plant_with_no_photograph_still_renders(blobs):
    """Deliberately an image rather than an empty gap: a card without one would be
    shorter than its neighbours, which is the unevenness the fixed aspect removes."""
    from ui.components.plant_photo import render_plant_photo

    render_plant_photo(None, blobs, OWNER)  # must not raise
