"""Photographs built to declare exactly what a test needs them to declare.

Real photographs are the wrong material for this. `test_pics/` carries genuine capture dates
and — until they were stripped on 2026-08-26 — a genuine position, which is unusable in two
ways: it is somebody's home, and a test cannot assert that 52.51 rounds to 52.5 without
writing their address into a test file.

So these are drawn, given the metadata the test is about, and thrown away. The coordinates
below are a stretch of the North Sea, chosen so that nothing here is anywhere.
"""

from datetime import datetime
from io import BytesIO

from PIL import Image

# Somewhere in the North Sea, and deliberately: a fixture that named a real town would
# invite somebody to check it against a real place, which is not what any of these test.
# Rounds to (54.5, 3.2) at one decimal place, and the third decimal is there so that a test
# of the coarsening has something to lose.
NOWHERE_LATITUDE = 54.512345
NOWHERE_LONGITUDE = 3.234567

_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769
_DATE_TIME_ORIGINAL = 0x9003
_ORIENTATION = 0x0112


def photograph(
    *,
    captured_at: datetime | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    orientation: int | None = None,
    size: tuple[int, int] = (24, 16),
) -> bytes:
    """A small JPEG declaring what it was asked to declare, and nothing else.

    Args:
        captured_at: Written as `DateTimeOriginal`, in EXIF's own format.
        latitude, longitude: Written as a signed decimal, converted to the
            degrees/minutes/seconds triple EXIF actually stores. Both or neither.
        orientation: Written as the orientation tag, for tests about normalisation.
        size: Deliberately tiny. Nothing here looks at pixels.
    """
    image = Image.new("RGB", size, color=(60, 120, 60))
    exif = image.getexif()

    if orientation is not None:
        exif[_ORIENTATION] = orientation

    if captured_at is not None:
        exif.get_ifd(_EXIF_IFD)[_DATE_TIME_ORIGINAL] = captured_at.strftime("%Y:%m:%d %H:%M:%S")

    if latitude is not None and longitude is not None:
        gps = exif.get_ifd(_GPS_IFD)
        gps[1] = "N" if latitude >= 0 else "S"
        gps[2] = _sexagesimal(abs(latitude))
        gps[3] = "E" if longitude >= 0 else "W"
        gps[4] = _sexagesimal(abs(longitude))

    written = BytesIO()
    image.save(written, format="JPEG", exif=exif.tobytes())
    return written.getvalue()


def _sexagesimal(decimal: float) -> tuple[float, float, float]:
    """A decimal degree as the degrees, minutes and seconds EXIF stores."""
    degrees = int(decimal)
    remainder = (decimal - degrees) * 60
    minutes = int(remainder)
    seconds = (remainder - minutes) * 60
    return (float(degrees), float(minutes), round(seconds, 4))
