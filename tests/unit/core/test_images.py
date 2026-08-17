"""Tests for upload storage, and for the EXIF orientation it normalises away."""

import base64
from io import BytesIO

from PIL import Image

from core.config import Settings
from core.images import store_upload, upright_bytes

# A landscape frame, so a quarter turn is visible in the dimensions alone.
_SIZE = (40, 20)


def _settings(**overrides) -> Settings:
    return Settings(openrouter_api_key="sk-test", _env_file=None, **overrides)


def _jpeg(orientation: int | None = None) -> bytes:
    """A decodable JPEG, optionally carrying an EXIF orientation tag."""
    image = Image.new("RGB", _SIZE, (10, 120, 40))
    buffer = BytesIO()
    if orientation is None:
        image.save(buffer, format="JPEG")
    else:
        exif = Image.Exif()
        exif[0x0112] = orientation
        image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def _size(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as image:
        return image.size


class TestUprightBytes:
    def test_a_quarter_turn_is_applied_to_the_pixels(self):
        """Orientation 6 — the value every sampled phone upload carried — means the
        stored landscape pixels are really a portrait photo."""
        assert _size(upright_bytes(_jpeg(orientation=6))) == (20, 40)

    def test_the_tag_is_cleared_so_nothing_turns_the_image_twice(self):
        """Anything downstream that honours EXIF must find nothing left to do."""
        turned = upright_bytes(_jpeg(orientation=6))

        with Image.open(BytesIO(turned)) as image:
            assert image.getexif().get(0x0112, 1) in (0, 1)

    def test_a_photo_needing_no_turn_is_returned_byte_identical(self):
        """The common case must not pay a re-encode, which would cost quality for
        nothing."""
        data = _jpeg()

        assert upright_bytes(data) is data

    def test_an_orientation_of_one_is_also_left_alone(self):
        data = _jpeg(orientation=1)

        assert upright_bytes(data) is data

    def test_bytes_that_cannot_be_decoded_pass_straight_through(self):
        """``validate_upload`` decides what counts as an image; this function must
        not start rejecting uploads that guard lets through."""
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

        assert upright_bytes(data) is data


class TestStoreUpload:
    def test_the_stored_file_is_upright(self, tmp_path):
        ref = store_upload(_jpeg(orientation=6), tmp_path, _settings())

        assert _size((tmp_path / f"{ref.ref}.jpeg").read_bytes()) == (20, 40)

    def test_the_model_sees_the_same_bytes_as_the_grid(self, tmp_path):
        """The base64 sent to the vision model and the file the My Plants card
        renders must be one image, or the two can disagree about which way up a
        plant is."""
        ref = store_upload(_jpeg(orientation=6), tmp_path, _settings())

        assert base64.b64decode(ref.data_b64) == (tmp_path / f"{ref.ref}.jpeg").read_bytes()

    def test_an_undecodable_upload_is_still_stored(self, tmp_path):
        """Unchanged behaviour, asserted so the pass-through above cannot regress
        into a rejection: several UI tests upload magic bytes with no real pixels."""
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

        ref = store_upload(data, tmp_path, _settings())

        assert (tmp_path / f"{ref.ref}.png").read_bytes() == data
