"""What a photograph is allowed to say about itself.

Two things are read and everything else is ignored: when it was taken, and roughly where.
Cameras write a great deal more — lens, exposure, serial numbers, sometimes a thumbnail of
the original frame — and none of it is used here, so none of it is read.

**The precise position never leaves this module.** It is rounded where it is read, and the
unrounded value exists only as a local. Nothing downstream is handed it, which is the only
reliable way to be sure nothing downstream stores it: a coarsening applied later is a
coarsening somebody can forget, and a database that never held a home address cannot leak
one.

**Nothing here raises.** Most photographs carry none of this — messaging apps strip metadata,
browser camera capture frequently has none, a screen grab never did — so absence is the
ordinary case rather than an error, and a malformed block is a photograph somebody still
wants diagnosed.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO

from PIL import Image

logger = logging.getLogger(__name__)

# EXIF tags, by number rather than by name: Pillow's name table is keyed on the same
# integers and the numbers are the stable half of the standard.
_GPS_IFD = 0x8825
_DATE_TIME_ORIGINAL = 0x9003  # when the shutter fired
_DATE_TIME = 0x0132  # when the file was last written; the fallback

_GPS_LATITUDE_REF = 1
_GPS_LATITUDE = 2
_GPS_LONGITUDE_REF = 3
_GPS_LONGITUDE = 4

# One decimal degree: about eleven kilometres of latitude, less of longitude away from the
# equator. Weather at that distance is indistinguishable from weather at the doorstep, which
# is the only thing this position is for — and it describes a district rather than an
# address.
_PRECISION = 1

# The bounds a capture date has to fall inside to be believed. A date in the future is a
# camera whose clock was never set; one before digital photography is the same fault the
# other way, and both produce a weather window for a time the plant was never in.
_EARLIEST = datetime(1990, 1, 1, tzinfo=UTC)

_EXIF_FORMAT = "%Y:%m:%d %H:%M:%S"


@dataclass(frozen=True, slots=True)
class Position:
    """Where a photograph was taken, to about eleven kilometres.

    There is no constructor here that takes a precise position: the rounding happens in
    ``_position_from`` and the fine value is never packaged up, so there is nothing to pass
    around by accident.
    """

    latitude: float
    longitude: float

    def __str__(self) -> str:
        return f"{self.latitude}, {self.longitude}"


@dataclass(frozen=True, slots=True)
class PhotographMetadata:
    """What one photograph declared, after everything unusable was discarded."""

    captured_at: datetime | None = None
    position: Position | None = None

    def __bool__(self) -> bool:
        return self.captured_at is not None or self.position is not None


NOTHING = PhotographMetadata()


def read(data: bytes, *, now: datetime | None = None) -> PhotographMetadata:
    """Read what a photograph declares, or return ``NOTHING``.

    Args:
        data: The image bytes **as uploaded**. Not the bytes stored afterwards:
            ``core.images.upright_bytes`` re-saves the file to apply its orientation, which
            clears the orientation tag deliberately and takes an unpredictable amount of the
            rest of the block with it.
        now: The moment to judge a capture date against. Injected rather than read here
            because a date test that reads the wall clock passes for a year and then does
            not.

    Returns:
        What could be read and believed. Never raises.
    """
    try:
        with Image.open(BytesIO(data)) as opened:
            exif = opened.getexif()
    except Exception as exc:  # noqa: BLE001 - a photograph is not less diagnosable for this
        logger.debug("no readable metadata: %s", exc)
        return NOTHING

    return PhotographMetadata(
        captured_at=_captured_at(exif, now or datetime.now(UTC)),
        position=_position_from(exif),
    )


def carries_a_position(data: bytes) -> bool:
    """Whether these bytes still declare where they were taken."""
    return read(data).position is not None


def without_position(data: bytes) -> bytes:
    """The same photograph, with no position left in the file.

    **The coarsening protects the column; this protects the file.** Rounding a position to
    eleven kilometres before writing it to `observations` does nothing about the precise
    fix sitting in the uploaded bytes — and those bytes are stored too. A row saying "near
    Frankfurt" beside a photograph saying "this doorstep" is not a coarsened position, it is
    a precise one with a coarsened label.

    **Costs nothing when there is nothing to remove**, which is most uploads: messaging apps
    strip metadata, browser capture rarely has any. Only a photograph that actually carries
    a position is re-encoded, so the ordinary upload keeps its exact original bytes and the
    project's standing promise that nothing resamples what the model sees.

    Returns the original bytes when they cannot be decoded at all — `validate_upload` is the
    gate on what counts as an image, and something unopenable has no metadata to leak.
    """
    if not carries_a_position(data):
        return data

    # Cut the metadata segment out rather than re-encoding around it. Re-saving through
    # Pillow works and costs something this project has decided not to spend: even at
    # identical quantisation tables the picture is decoded and re-encoded, and the pixels
    # that come out are not the pixels that went in. `store_upload` promises the model sees
    # what the owner uploaded, and a privacy fix is not a licence to quietly resample it.
    stripped = _jpeg_without_metadata(data)

    if stripped is None:
        # Not a JPEG, or one this cannot parse. Re-encoding is then the only tool left, and
        # a slightly resampled photograph is a better outcome than a stored address.
        stripped = _resaved_without_metadata(data)

    if stripped is None or carries_a_position(stripped):
        # Nothing worked. Say so loudly: storing the original would be storing somebody's
        # doorstep, and doing that quietly is the failure this whole function exists to
        # prevent.
        logger.error("could not remove the position from an upload; refusing to store it")
        raise PositionCannotBeRemovedError

    return stripped


class PositionCannotBeRemovedError(RuntimeError):
    """An upload declares a position that could not be taken out of it.

    Raised rather than swallowed. Every other failure in this module returns nothing and
    lets the diagnosis carry on, because the cost of those is a missing hint. The cost of
    this one is a precise home address on disk, which is not a degraded feature — it is the
    thing the coarsening exists to prevent, arriving by another door.
    """


# JPEG markers whose payload is metadata rather than picture. `APP1` carries Exif — which
# is where a position lives — and XMP, which can carry a copy of it. `APP13` carries IPTC,
# which has location fields of its own.
#
# Deliberately not dropped: `APP2` (ICC colour profiles) and `APP14` (Adobe colour
# transform). Both change how the picture is interpreted, and removing them to protect a
# position would alter the photograph to fix its metadata.
_METADATA_MARKERS = frozenset({0xE1, 0xED})

_STANDALONE_MARKERS = frozenset({0x01, *range(0xD0, 0xD9)})


def _jpeg_without_metadata(data: bytes) -> bytes | None:
    """A JPEG with its metadata segments removed and its picture untouched.

    Returns ``None`` when the bytes are not a JPEG or do not parse as one, so the caller can
    fall back rather than guessing.

    A JPEG is a sequence of marker segments followed by entropy-coded scan data. Copying
    every segment except the metadata ones, verbatim, produces a file whose picture is bit
    for bit what arrived — no decode, no re-encode, nothing to lose.
    """
    if not data.startswith(b"\xff\xd8"):
        return None

    out = bytearray(data[:2])
    index = 2
    end = len(data)

    while index + 1 < end:
        if data[index] != 0xFF:
            return None  # Not where a marker should be; do not guess.

        marker = data[index + 1]

        if marker == 0xFF:  # Fill byte before the real marker.
            index += 1
            continue

        if marker in _STANDALONE_MARKERS:
            out += data[index : index + 2]
            index += 2
            continue

        if marker == 0xDA:  # Start of scan: the picture itself, to the end of the file.
            out += data[index:]
            return bytes(out)

        if index + 3 >= end:
            return None

        length = (data[index + 2] << 8) | data[index + 3]
        if length < 2 or index + 2 + length > end:
            return None

        if marker not in _METADATA_MARKERS:
            out += data[index : index + 2 + length]
        index += 2 + length

    return bytes(out)


def _resaved_without_metadata(data: bytes) -> bytes | None:
    """The fallback: decode and write it out again, with no metadata attached.

    Loses a little of the picture to re-encoding, which is why it is the fallback rather
    than the method.
    """
    try:
        with Image.open(BytesIO(data)) as opened:
            image_format = opened.format
            opened.load()
            saved = BytesIO()
            opened.save(saved, format=image_format, exif=b"")
            return saved.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not re-save an upload without its metadata: %s", exc)
        return None


def earliest(readings: list[PhotographMetadata]) -> PhotographMetadata:
    """Combine what several photographs of one plant declared.

    The earliest capture date, because an upload is one observation and the earliest is the
    one whose weather window covers all of them. The first position found, because
    photographs taken minutes apart in one garden round to the same place anyway, and two
    that do not are a person who photographed a plant somewhere else — which the owner can
    correct, and which no rule here could decide better.
    """
    dates = [reading.captured_at for reading in readings if reading.captured_at]
    positions = [reading.position for reading in readings if reading.position]

    return PhotographMetadata(
        captured_at=min(dates) if dates else None,
        position=positions[0] if positions else None,
    )


def _captured_at(exif, now: datetime) -> datetime | None:
    """When the shutter fired, if the photograph says so plausibly."""
    raw = _exif_value(exif, _DATE_TIME_ORIGINAL) or exif.get(_DATE_TIME)
    if not isinstance(raw, str):
        return None

    try:
        # EXIF dates carry no timezone. Read as UTC rather than as local time: the reader is
        # a server that has no idea where the camera was, and inventing an offset would move
        # a date across a day boundary for people east of it.
        taken = datetime.strptime(raw.strip(), _EXIF_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        logger.debug("unparseable capture date: %r", raw)
        return None

    if taken > now or taken < _EARLIEST:
        logger.debug("implausible capture date, ignoring: %s", taken)
        return None

    return taken


def _exif_value(exif, tag: int):
    """A tag from the Exif sub-directory, which is where the interesting dates live."""
    try:
        return exif.get_ifd(0x8769).get(tag)
    except Exception:  # noqa: BLE001 - a malformed sub-directory is a photograph with none
        return None


def _position_from(exif) -> Position | None:
    """The coarsened position, or nothing.

    **This is the only place a precise position exists**, and it exists as two locals that
    go out of scope at the return. See the module docstring.
    """
    try:
        gps = exif.get_ifd(_GPS_IFD)
    except Exception:  # noqa: BLE001
        return None

    if not gps:
        return None

    latitude = _degrees(gps.get(_GPS_LATITUDE), gps.get(_GPS_LATITUDE_REF), "S")
    longitude = _degrees(gps.get(_GPS_LONGITUDE), gps.get(_GPS_LONGITUDE_REF), "W")
    if latitude is None or longitude is None:
        return None

    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        logger.debug("position outside the world, ignoring")
        return None

    return Position(latitude=round(latitude, _PRECISION), longitude=round(longitude, _PRECISION))


def _degrees(value, ref, negative: str) -> float | None:
    """One coordinate, from EXIF's degrees/minutes/seconds triple to a signed decimal."""
    try:
        degrees, minutes, seconds = (float(part) for part in value)
    except (TypeError, ValueError):
        return None

    decimal = degrees + minutes / 60 + seconds / 3600
    if isinstance(ref, str) and ref.strip().upper().startswith(negative):
        decimal = -decimal
    return decimal
