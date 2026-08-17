"""Upload handling: validate, store outside the served path, return a reference."""

import base64
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from agent.state import ImageRef
from core.config import Settings
from core.guards import validate_upload

_MEDIA_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

# EXIF tag 0x0112. Values other than 1 mean the stored pixels need turning; 0 is
# not a legal value but appears in the wild, and means the same as "nothing to do".
_ORIENTATION_TAG = 0x0112
_UPRIGHT = (0, 1)


def upright_bytes(data: bytes) -> bytes:
    """Apply an image's EXIF orientation tag to its pixels.

    A phone camera writes the sensor's raw landscape pixels and records the quarter
    turn separately, in EXIF. Nothing downstream applies that tag on its own, so
    without this the vision model reads plants lying on their side — every upload
    sampled from ``data/uploads`` carried orientation 6.

    Returns ``data`` unchanged when there is no turn to apply, so the common case
    costs no re-encode and loses no quality. Also returns it unchanged when the
    bytes cannot be decoded: ``validate_upload`` is the gate on what counts as an
    image, and this function is not the place to start rejecting uploads it lets
    through.
    """
    try:
        with Image.open(BytesIO(data)) as opened:
            if opened.getexif().get(_ORIENTATION_TAG, 1) in _UPRIGHT:
                return data
            image_format = opened.format
            # exif_transpose clears the tag it just honoured, so the result is not
            # turned a second time by anything that reads EXIF later — including
            # ui/components/plant_photo.py, which still needs to correct the
            # photos uploaded before this function existed.
            turned = ImageOps.exif_transpose(opened)
            buffer = BytesIO()
            # Re-encoded at the source format so the file extension, the media
            # type and the bytes stay in agreement.
            turned.save(buffer, format=image_format, quality=95)
    except Exception:  # noqa: BLE001 — see the docstring: not this function's gate
        return data
    return buffer.getvalue()


def store_upload(data: bytes, upload_dir: Path, settings: Settings) -> ImageRef:
    """Validate an upload, persist it under an opaque id, and return a reference.

    The stored file and the base64 the model sees are the same upright bytes, so
    the grid and the diagnosis can never disagree about which way up a plant is.

    Raises:
        UploadRejected: if validation fails.
    """
    image_format = validate_upload(data, settings)
    # After validation, not before: the size limit governs what the owner submits,
    # and normalisation is our own transformation of an upload already accepted.
    data = upright_bytes(data)

    upload_dir.mkdir(parents=True, exist_ok=True)
    ref = uuid.uuid4().hex
    (upload_dir / f"{ref}.{image_format}").write_bytes(data)

    return ImageRef(
        ref=ref,
        media_type=_MEDIA_TYPES[image_format],
        data_b64=base64.b64encode(data).decode("ascii"),
    )
