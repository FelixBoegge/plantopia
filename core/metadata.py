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
