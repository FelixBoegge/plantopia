"""Tests for the My Plants card photograph."""

import pytest
from PIL import Image

from ui.components.plant_photo import _ASPECT

pytestmark = pytest.mark.ui


def _write(path, size):
    Image.new("RGB", size, (10, 120, 40)).save(path)


def test_a_missing_reference_resolves_to_nothing(tmp_path):
    from ui.components.plant_photo import resolve_photo

    assert resolve_photo(None, tmp_path) is None


def test_a_reference_resolves_without_knowing_the_extension(tmp_path):
    """``plants.photo_ref`` stores only the uuid stem — the extension is not recorded."""
    from ui.components.plant_photo import resolve_photo

    _write(tmp_path / "abc123.jpeg", (40, 30))

    assert resolve_photo("abc123", tmp_path) == tmp_path / "abc123.jpeg"


def test_a_reference_whose_file_was_deleted_resolves_to_nothing(tmp_path):
    """The uploads directory is gitignored scratch; a missing file is normal."""
    from ui.components.plant_photo import resolve_photo

    assert resolve_photo("abc123", tmp_path) is None


@pytest.mark.parametrize(
    "size", [(1200, 1600), (1600, 1200), (800, 800)], ids=["portrait", "landscape", "square"]
)
def test_every_orientation_crops_to_one_aspect_ratio(tmp_path, size):
    """The point of cropping: equal-width columns then give equal image heights,
    so a portrait phone photo cannot make its card twice as tall as its neighbours."""
    from io import BytesIO

    from ui.components.plant_photo import _banner_bytes

    path = tmp_path / "photo.png"
    _write(path, size)

    with Image.open(BytesIO(_banner_bytes.__wrapped__(str(path), 0.0))) as banner:
        assert banner.width / banner.height == pytest.approx(_ASPECT, abs=0.01)


def test_the_placeholder_matches_the_photo_aspect_ratio():
    """A card without a photo must not be shorter than its neighbours."""
    from io import BytesIO

    from ui.components.plant_photo import _placeholder_bytes

    with Image.open(BytesIO(_placeholder_bytes.__wrapped__())) as tile:
        assert tile.width / tile.height == pytest.approx(_ASPECT, abs=0.01)


def test_a_corrupt_upload_falls_back_instead_of_raising():
    """A bad image should cost a thumbnail, not the whole plant grid.

    Self-contained because ``AppTest.from_function`` executes only the function's
    own source: a reference to anything defined at module scope would raise
    ``NameError`` inside the script rather than testing what it looks like it tests.
    """
    from streamlit.testing.v1 import AppTest

    def script():
        import tempfile
        from pathlib import Path

        from ui.components.plant_photo import render_plant_photo

        directory = Path(tempfile.mkdtemp())
        (directory / "broken.jpeg").write_bytes(b"not an image")
        render_plant_photo("broken", directory)

    app = AppTest.from_function(script).run()

    # ``AppTest`` exposes no accessor for image elements, so the absence of an
    # exception is the assertion: without the fallback, Pillow's decode error
    # would propagate out of the script and land here.
    assert not app.exception
