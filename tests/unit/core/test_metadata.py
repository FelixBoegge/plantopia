"""What a photograph is allowed to say about itself.

The proportions here follow the risk. One test reads a well-formed photograph; the rest are
about photographs that say nothing, say nonsense, or say something that must not be believed
— because that is most photographs, and because the one thing this module must never do is
fail an upload somebody wanted diagnosed.

The fixtures are drawn rather than photographed. See `tests/fakes/photographs.py` for why:
a real photograph's coordinates are somebody's home, and a test cannot assert that they round
correctly without writing them down.
"""

from datetime import UTC, datetime, timedelta

import pytest

from core.metadata import NOTHING, PhotographMetadata, Position, earliest, read
from tests.fakes.photographs import NOWHERE_LATITUDE, NOWHERE_LONGITUDE, photograph

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
TAKEN = datetime(2026, 8, 10, 10, 50, 49, tzinfo=UTC)


class TestAPhotographThatKnowsThings:
    def test_reads_the_capture_date(self):
        found = read(photograph(captured_at=TAKEN), now=NOW)

        assert found.captured_at == TAKEN

    def test_reads_the_position(self):
        found = read(photograph(latitude=NOWHERE_LATITUDE, longitude=NOWHERE_LONGITUDE), now=NOW)

        assert found.position == Position(latitude=54.5, longitude=3.2)

    def test_reads_both_at_once(self):
        found = read(
            photograph(captured_at=TAKEN, latitude=NOWHERE_LATITUDE, longitude=NOWHERE_LONGITUDE),
            now=NOW,
        )

        assert found.captured_at == TAKEN
        assert found.position is not None

    def test_a_real_photograph_from_the_repository(self):
        """The drawn fixtures could all be wrong together — they are written and read by
        code that agrees with itself. This one came out of a phone."""
        import pathlib

        data = pathlib.Path("test_pics/20260810_105048.jpg").read_bytes()

        found = read(data, now=NOW)

        assert found.captured_at == datetime(2026, 8, 10, 10, 50, 49, tzinfo=UTC)


class TestTheCoarsening:
    def test_keeps_only_one_decimal_place(self):
        found = read(photograph(latitude=54.512345, longitude=3.234567), now=NOW)

        assert found.position == Position(latitude=54.5, longitude=3.2)

    def test_the_precise_position_is_not_anywhere_in_what_comes_back(self):
        """The property the whole design rests on. A coarsening applied later is one
        somebody can forget; this one happens where the value is read, and the fine value
        never leaves the function."""
        found = read(photograph(latitude=54.512345, longitude=3.234567), now=NOW)

        rendered = repr(found)
        assert "54.512345" not in rendered
        assert "3.234567" not in rendered
        assert "512345" not in rendered

    @pytest.mark.parametrize(
        ("latitude", "longitude", "expected"),
        [
            (54.512345, 3.234567, (54.5, 3.2)),
            (-33.865143, 151.209900, (-33.9, 151.2)),
            (40.712776, -74.005974, (40.7, -74.0)),
            (-22.906847, -43.172896, (-22.9, -43.2)),
        ],
        ids=["north-east", "south-east", "north-west", "south-west"],
    )
    def test_every_corner_of_the_world(self, latitude, longitude, expected):
        """EXIF stores a magnitude and a hemisphere letter separately, so the sign is
        reconstructed rather than read — and getting it wrong puts somebody's plant in the
        opposite hemisphere, where the seasons are inverted."""
        found = read(photograph(latitude=latitude, longitude=longitude), now=NOW)

        assert found.position == Position(*expected)


class TestADateThatCannotBeTrue:
    def test_a_date_in_the_future_is_ignored(self):
        """A camera whose clock was never set. Believed, it asks for weather that has not
        happened."""
        found = read(photograph(captured_at=NOW + timedelta(days=2)), now=NOW)

        assert found.captured_at is None

    def test_a_date_before_digital_photography_is_ignored(self):
        found = read(photograph(captured_at=datetime(1972, 5, 1, tzinfo=UTC)), now=NOW)

        assert found.captured_at is None

    def test_a_date_a_moment_ago_is_believed(self):
        """The boundary matters in the direction that keeps working photographs working."""
        taken = NOW - timedelta(minutes=1)

        found = read(photograph(captured_at=taken), now=NOW)

        assert found.captured_at == taken

    def test_an_old_but_plausible_date_is_believed(self):
        taken = datetime(2011, 3, 4, 9, 30, tzinfo=UTC)

        found = read(photograph(captured_at=taken), now=NOW)

        assert found.captured_at == taken


class TestAPhotographThatSaysNothing:
    """None of these may raise. Most photographs are in one of these states."""

    def test_no_metadata_at_all(self):
        assert read(photograph(), now=NOW) == NOTHING

    def test_bytes_that_are_not_an_image(self):
        assert read(b"this is not a photograph", now=NOW) == NOTHING

    def test_empty_bytes(self):
        assert read(b"", now=NOW) == NOTHING

    def test_a_truncated_image(self):
        whole = photograph(captured_at=TAKEN)

        assert read(whole[: len(whole) // 3], now=NOW) == NOTHING

    def test_a_position_with_no_longitude(self):
        """Half a position is not a position."""
        found = read(photograph(latitude=NOWHERE_LATITUDE), now=NOW)

        assert found.position is None

    def test_a_position_outside_the_world(self):
        found = read(photograph(latitude=1234.0, longitude=99.0), now=NOW)

        assert found.position is None

    def test_nothing_is_falsy(self):
        """So a caller can ask `if metadata:` rather than checking two fields."""
        assert not read(photograph(), now=NOW)
        assert read(photograph(captured_at=TAKEN), now=NOW)


class TestSeveralPhotographsOfOnePlant:
    def test_the_earliest_date_wins(self):
        """An upload is one observation, and the earliest is the one whose weather window
        covers all of them."""
        readings = [
            PhotographMetadata(captured_at=datetime(2026, 8, 12, tzinfo=UTC)),
            PhotographMetadata(captured_at=datetime(2026, 8, 10, tzinfo=UTC)),
            PhotographMetadata(captured_at=datetime(2026, 8, 11, tzinfo=UTC)),
        ]

        assert earliest(readings).captured_at == datetime(2026, 8, 10, tzinfo=UTC)

    def test_one_photograph_without_a_date_does_not_erase_the_others(self):
        readings = [
            PhotographMetadata(),
            PhotographMetadata(captured_at=datetime(2026, 8, 10, tzinfo=UTC)),
        ]

        assert earliest(readings).captured_at == datetime(2026, 8, 10, tzinfo=UTC)

    def test_the_first_position_found_is_used(self):
        readings = [
            PhotographMetadata(),
            PhotographMetadata(position=Position(54.5, 3.2)),
            PhotographMetadata(position=Position(40.7, -74.0)),
        ]

        assert earliest(readings).position == Position(54.5, 3.2)

    def test_nothing_at_all(self):
        assert earliest([PhotographMetadata(), PhotographMetadata()]) == NOTHING

    def test_no_photographs(self):
        assert earliest([]) == NOTHING


class TestTakingThePositionOutOfTheFile:
    """The coarsening protects the column. This protects the file.

    Rounding to eleven kilometres before writing `observations.latitude` does nothing about
    the precise fix still sitting in the uploaded bytes — and those bytes are stored too. A
    row saying "near Frankfurt" beside a photograph saying "this doorstep" is not a
    coarsened position; it is a precise one with a coarsened label.
    """

    def test_a_photograph_that_carried_one_no_longer_does(self):
        from core.metadata import without_position

        with_position = photograph(
            captured_at=TAKEN, latitude=NOWHERE_LATITUDE, longitude=NOWHERE_LONGITUDE
        )

        assert read(without_position(with_position), now=NOW).position is None

    def test_the_picture_itself_is_untouched(self):
        """Byte for byte, not merely visually. This project promises the model sees what
        the owner uploaded, and a privacy fix is not a licence to quietly resample it —
        re-encoding through Pillow passes an eye test and fails this one.
        """
        import hashlib
        from io import BytesIO

        from PIL import Image

        from core.metadata import without_position

        original = photograph(
            captured_at=TAKEN, latitude=NOWHERE_LATITUDE, longitude=NOWHERE_LONGITUDE
        )

        def pixels(data: bytes) -> str:
            with Image.open(BytesIO(data)) as opened:
                return hashlib.sha256(opened.convert("RGB").tobytes()).hexdigest()

        assert pixels(without_position(original)) == pixels(original)

    def test_a_real_photograph_from_a_phone(self):
        """The drawn fixtures are written and read by code that agrees with itself. This
        one came out of a phone, with a real GPS block, and is the backup taken before
        `test_pics/` was stripped."""
        import hashlib
        import pathlib
        from io import BytesIO

        from PIL import Image

        from core.metadata import without_position

        source = pathlib.Path("tests/fixtures/phone_with_position.jpg")
        original = source.read_bytes()
        assert read(original, now=NOW).position is not None, "the fixture lost its position"

        stripped = without_position(original)

        def pixels(data: bytes) -> str:
            with Image.open(BytesIO(data)) as opened:
                return hashlib.sha256(opened.convert("RGB").tobytes()).hexdigest()

        assert read(stripped, now=NOW).position is None
        assert pixels(stripped) == pixels(original)

    def test_a_photograph_that_never_had_one_is_returned_untouched(self):
        """Most uploads. Messaging apps strip metadata and browser capture rarely has any,
        so the ordinary photograph keeps its exact original bytes and pays nothing."""
        from core.metadata import without_position

        plain = photograph(captured_at=TAKEN)

        assert without_position(plain) is plain

    def test_it_refuses_rather_than_storing_a_position_it_cannot_remove(self, monkeypatch):
        """Every other failure here returns nothing and lets the diagnosis carry on, because
        the cost is a missing hint. The cost of this one is an address on disk."""
        import pytest

        from core import metadata

        monkeypatch.setattr(metadata, "_jpeg_without_metadata", lambda data: None)
        monkeypatch.setattr(metadata, "_resaved_without_metadata", lambda data: None)

        with_position = photograph(latitude=NOWHERE_LATITUDE, longitude=NOWHERE_LONGITUDE)

        with pytest.raises(metadata.PositionCannotBeRemovedError):
            metadata.without_position(with_position)
