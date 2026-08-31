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

        stored = store_upload(
            _jpeg(orientation=6), blobs=store, user_id=blob_owner, settings=_settings()
        )

        assert _size(store.get(blob_owner, stored.ref.ref)) == (20, 40)

    def test_the_model_sees_exactly_what_was_stored(self, pg_session, blob_owner):
        """One image, not two. The bytes the vision model is shown and the bytes the My
        Plants card renders are the same row, so they cannot disagree about which way up
        a plant is."""
        store = PostgresBlobStore(pg_session)

        stored = store_upload(
            _jpeg(orientation=6), blobs=store, user_id=blob_owner, settings=_settings()
        )

        stored = store.get(blob_owner, stored.ref.ref)
        assert stored == upright_bytes(_jpeg(orientation=6))

    def test_nothing_is_downscaled(self, pg_session, blob_owner):
        """U3 is deliberately not bundled with this change: resizing alters what the
        vision model sees, and no measurement in this project can see the vision layer
        (M19), so the damage would be undetectable."""
        store = PostgresBlobStore(pg_session)
        original = _jpeg(orientation=1)

        stored = store_upload(original, blobs=store, user_id=blob_owner, settings=_settings())

        assert _size(store.get(blob_owner, stored.ref.ref)) == _size(original)

    def test_an_undecodable_upload_is_still_stored(self, pg_session, blob_owner):
        """Unchanged behaviour, asserted so the pass-through above cannot regress into a
        rejection: several UI tests upload magic bytes with no real pixels."""
        store = PostgresBlobStore(pg_session)
        data = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + bytes(32)

        stored = store_upload(data, blobs=store, user_id=blob_owner, settings=_settings())

        assert store.get(blob_owner, stored.ref.ref) == data

    def test_the_media_type_matches_the_format_detected(self, pg_session, blob_owner):
        store = PostgresBlobStore(pg_session)

        stored = store_upload(_jpeg(), blobs=store, user_id=blob_owner, settings=_settings())

        assert stored.ref.media_type == "image/jpeg"


@pytest.fixture
def blob_owner(pg_session):

    return make_user(pg_session).id


class TestWhatAnUploadDeclared:
    """The ordering constraint, and the reason this class exists at all.

    `upright_bytes` re-saves the file to apply its declared orientation, which clears the
    orientation tag on purpose and takes an unpredictable amount of the rest of the metadata
    block with it. Reading afterwards reads a file that no longer says anything.

    The two calls look independent, both are one line, and swapping them produces uploads
    that work perfectly and simply never carry a date or a place — a failure with no symptom
    except an absence nobody notices. This is the test that has to notice.
    """

    def test_what_the_photograph_declared_comes_back_with_it(self, pg_session, blob_owner):
        from datetime import UTC, datetime

        from tests.fakes.photographs import NOWHERE_LATITUDE, NOWHERE_LONGITUDE, photograph

        taken = datetime(2026, 8, 10, 10, 50, 49, tzinfo=UTC)
        store = PostgresBlobStore(pg_session)

        stored = store_upload(
            photograph(captured_at=taken, latitude=NOWHERE_LATITUDE, longitude=NOWHERE_LONGITUDE),
            blobs=store,
            user_id=blob_owner,
            settings=_settings(),
        )

        assert stored.metadata.captured_at == taken
        assert stored.metadata.position is not None

    def test_it_survives_a_photograph_that_needed_turning(self, pg_session, blob_owner):
        """The case the ordering is about. An upright photograph is never re-saved, so
        reading afterwards would appear to work — and every photograph out of a phone
        carries an orientation, which is what makes this the ordinary case rather than the
        edge one."""
        from datetime import UTC, datetime

        from tests.fakes.photographs import photograph

        taken = datetime(2026, 8, 10, 10, 50, 49, tzinfo=UTC)
        store = PostgresBlobStore(pg_session)

        stored = store_upload(
            photograph(captured_at=taken, orientation=6),
            blobs=store,
            user_id=blob_owner,
            settings=_settings(),
        )

        assert stored.metadata.captured_at == taken

    def test_the_stored_bytes_no_longer_declare_it(self, pg_session, blob_owner):
        """Not an assertion about what *should* happen — an assertion about what does, and
        therefore about why the read cannot be moved. If this ever stops being true, the
        ordering constraint has quietly stopped applying and this class can go."""
        from datetime import UTC, datetime

        from core.metadata import read
        from tests.fakes.photographs import photograph

        store = PostgresBlobStore(pg_session)
        original = photograph(
            captured_at=datetime(2026, 8, 10, 10, 50, 49, tzinfo=UTC), orientation=6
        )

        stored = store_upload(original, blobs=store, user_id=blob_owner, settings=_settings())

        assert read(store.get(blob_owner, stored.ref.ref)).captured_at is None

    def test_a_photograph_that_declares_nothing(self, pg_session, blob_owner):
        from core.metadata import NOTHING
        from tests.fakes.photographs import photograph

        store = PostgresBlobStore(pg_session)

        stored = store_upload(photograph(), blobs=store, user_id=blob_owner, settings=_settings())

        assert stored.metadata == NOTHING

    def test_a_refused_upload_is_never_read(self, pg_session, blob_owner):
        """The gate on what counts as an image is the gate on what gets examined. Reading
        metadata out of something the size limit rejected would mean parsing a file the
        system has already decided not to accept."""
        import pytest

        from core.guards import UploadRejected

        store = PostgresBlobStore(pg_session)
        settings = _settings()
        too_big = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + bytes(settings.max_upload_bytes + 1)

        with pytest.raises(UploadRejected):
            store_upload(too_big, blobs=store, user_id=blob_owner, settings=settings)


class TestWhatIsStoredCarriesNoPosition:
    """The coarsening protects the column; this protects the file.

    `upright_bytes` re-saves a photograph that needs turning, which incidentally drops its
    metadata — but it returns an upright one untouched, and every landscape photograph out
    of a phone is upright. Without this, those would land on disk with somebody's doorstep
    inside them, beside a row that reads "near Frankfurt".
    """

    def test_a_stored_photograph_declares_no_position(self, pg_session, blob_owner):
        from core.metadata import read
        from tests.fakes.photographs import NOWHERE_LATITUDE, NOWHERE_LONGITUDE, photograph

        store = PostgresBlobStore(pg_session)

        stored = store_upload(
            photograph(latitude=NOWHERE_LATITUDE, longitude=NOWHERE_LONGITUDE),
            blobs=store,
            user_id=blob_owner,
            settings=_settings(),
        )

        assert stored.metadata.position is not None, "it was read before it was removed"
        assert read(store.get(blob_owner, stored.ref.ref)).position is None

    def test_the_upright_case_too(self, pg_session, blob_owner):
        """The one `upright_bytes` returns unchanged, which is where the hole was."""
        from core.metadata import read
        from tests.fakes.photographs import NOWHERE_LATITUDE, NOWHERE_LONGITUDE, photograph

        store = PostgresBlobStore(pg_session)

        stored = store_upload(
            photograph(latitude=NOWHERE_LATITUDE, longitude=NOWHERE_LONGITUDE, orientation=1),
            blobs=store,
            user_id=blob_owner,
            settings=_settings(),
        )

        assert read(store.get(blob_owner, stored.ref.ref)).position is None

    def test_a_turned_photograph_is_still_delivered_upright(self, pg_session, blob_owner):
        """Both steps, in order. Stripping the metadata after the turn has been applied is
        safe; stripping it before would take the tag that says which way to turn, and every
        photograph out of a phone would reach the model lying on its side."""
        from tests.fakes.photographs import NOWHERE_LATITUDE, NOWHERE_LONGITUDE, photograph

        store = PostgresBlobStore(pg_session)

        stored = store_upload(
            photograph(
                latitude=NOWHERE_LATITUDE,
                longitude=NOWHERE_LONGITUDE,
                orientation=6,
                size=(24, 16),
            ),
            blobs=store,
            user_id=blob_owner,
            settings=_settings(),
        )

        assert _size(store.get(blob_owner, stored.ref.ref)) == (16, 24)
