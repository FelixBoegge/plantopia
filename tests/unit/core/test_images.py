"""Tests for upload storage, and for the EXIF orientation it normalises away."""

from io import BytesIO

import pytest
from PIL import Image

from core.blobs import PostgresBlobStore
from core.config import Settings
from core.images import store_upload, upright_bytes
from tests.people import make_user
from tests.secrets import TEST_JWT_SECRET

# A landscape frame, so a quarter turn is visible in the dimensions alone.
_SIZE = (40, 20)


def _settings(**overrides) -> Settings:
    return Settings(
        openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET, _env_file=None, **overrides
    )


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
    """Storage now goes through the blob port, so these assert on what came back out
    of it rather than on a file on disk."""

    def test_the_stored_bytes_are_upright(self, pg_session, blob_owner):
        store = PostgresBlobStore(pg_session)

        ref = store_upload(
            _jpeg(orientation=6), blobs=store, user_id=blob_owner, settings=_settings()
        )

        assert _size(store.get(blob_owner, ref.ref)) == (20, 40)

    def test_the_model_sees_exactly_what_was_stored(self, pg_session, blob_owner):
        """One image, not two. The bytes the vision model is shown and the bytes the My
        Plants card renders are the same row, so they cannot disagree about which way up
        a plant is."""
        store = PostgresBlobStore(pg_session)

        ref = store_upload(
            _jpeg(orientation=6), blobs=store, user_id=blob_owner, settings=_settings()
        )

        stored = store.get(blob_owner, ref.ref)
        assert stored == upright_bytes(_jpeg(orientation=6))

    def test_nothing_is_downscaled(self, pg_session, blob_owner):
        """U3 is deliberately not bundled with this change: resizing alters what the
        vision model sees, and no measurement in this project can see the vision layer
        (M19), so the damage would be undetectable."""
        store = PostgresBlobStore(pg_session)
        original = _jpeg(orientation=1)

        ref = store_upload(original, blobs=store, user_id=blob_owner, settings=_settings())

        assert _size(store.get(blob_owner, ref.ref)) == _size(original)

    def test_an_undecodable_upload_is_still_stored(self, pg_session, blob_owner):
        """Unchanged behaviour, asserted so the pass-through above cannot regress into a
        rejection: several UI tests upload magic bytes with no real pixels."""
        store = PostgresBlobStore(pg_session)
        data = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + bytes(32)

        ref = store_upload(data, blobs=store, user_id=blob_owner, settings=_settings())

        assert store.get(blob_owner, ref.ref) == data

    def test_the_media_type_matches_the_format_detected(self, pg_session, blob_owner):
        store = PostgresBlobStore(pg_session)

        ref = store_upload(_jpeg(), blobs=store, user_id=blob_owner, settings=_settings())

        assert ref.media_type == "image/jpeg"


@pytest.fixture
def blob_owner(pg_session):

    return make_user(pg_session).id
