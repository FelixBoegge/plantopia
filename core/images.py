"""Upload handling: validate, read what the file declares, normalise, strip, store.

**That order is a correctness constraint, not a preference.** ``upright_bytes`` re-saves the
file to apply its declared orientation, which clears the orientation tag deliberately — so
nothing turns the image twice — and takes an unpredictable amount of the rest of the metadata
block with it. Anything to be learned from a photograph has to be learned from the bytes as
they arrived.

The two operations look independent, both are one line, and swapping them produces uploads
that work perfectly and simply never carry a date or a place. So they live in one function
rather than in a rule two callers have to remember, and
``tests/unit/core/test_images.py`` fails if the order is ever reversed.
"""

from dataclasses import dataclass
from io import BytesIO
from uuid import UUID

from PIL import Image, ImageOps

from agent.state import ImageRef
from core.blobs import BlobStore
from core.config import Settings
from core.guards import validate_upload
from core.metadata import PhotographMetadata, without_position
from core.metadata import read as read_metadata

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
            # turned a second time by anything that reads EXIF later.
            turned = ImageOps.exif_transpose(opened)
            buffer = BytesIO()
            # Re-encoded at the source format so the file extension, the media
            # type and the bytes stay in agreement.
            turned.save(buffer, format=image_format, quality=95)
    except Exception:  # noqa: BLE001 — see the docstring: not this function's gate
        return data
    return buffer.getvalue()


def downscaled(data: bytes, *, max_edge: int) -> bytes:
    """Cap an image's long edge, preserving its aspect ratio.

    Returns ``data`` unchanged when it already fits, so the common case costs no
    re-encode and loses no quality — the same bargain ``upright_bytes`` makes for a
    photograph that needs no turning.

    **Cost, not accuracy.** Four 8 MB photographs reach the vision model at full
    resolution today, and the models downscale above this edge themselves, so the pixels
    above it are billed and discarded. No measurement in this project can see the vision
    layer (``M19``), so this deliberately claims nothing about what the model concludes.

    Returns ``data`` unchanged when the bytes cannot be decoded: ``validate_upload`` is
    the gate on what counts as an image, and this is not the place to start rejecting
    uploads it let through.
    """
    try:
        with Image.open(BytesIO(data)) as opened:
            if max(opened.size) <= max_edge:
                return data
            image_format = opened.format
            # `thumbnail` caps the long edge and keeps the ratio, in place.
            copy = opened.copy()
            copy.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            copy.save(buffer, format=image_format, quality=95)
    except Exception:  # noqa: BLE001 — see the docstring: not this function's gate
        return data
    return buffer.getvalue()


@dataclass(frozen=True, slots=True)
class StoredPhotograph:
    """A stored photograph and whatever it declared before it was normalised.

    The two travel together because they are produced together and for the same reason: by
    the time a caller has the reference, the bytes that carried the metadata are gone.
    """

    ref: ImageRef
    metadata: PhotographMetadata


def store_upload(
    data: bytes, *, blobs: BlobStore, user_id: UUID, settings: Settings
) -> StoredPhotograph:
    """Validate an upload, read what it declares, store it, and return both.

    The stored bytes and the bytes the model sees are the same upright, capped bytes, so
    the grid and the diagnosis can never disagree about which way up a plant is.

    **Downscaled to ``max_image_edge_px``.** Pillow applies the declared orientation and
    caps the long edge; nothing else. The cap is cost rather than accuracy — see
    ``downscaled`` — and it runs after the metadata read for the reason this module's
    docstring gives.

    Raises:
        UploadRejected: if validation fails.
    """
    image_format = validate_upload(data, settings)

    # **Before `upright_bytes`, which destroys what this reads.** Also after validation,
    # so a refused upload is never examined: the gate on what counts as an image is the
    # gate on what gets looked at.
    declared = read_metadata(data)

    # After validation, not before: the size limit governs what the owner submits,
    # and normalisation is our own transformation of an upload already accepted.
    data = upright_bytes(data)

    # After `read_metadata`, which needs the bytes as they arrived, and beside
    # `upright_bytes` for the same reason: both re-encode, and a re-encode is what
    # destroys the metadata block.
    data = downscaled(data, max_edge=settings.max_image_edge_px)

    # **And the position comes out of the file before the file is stored.** Coarsening the
    # number written to `observations` protects the column and does nothing about the
    # precise fix still sitting in the bytes — which are stored too, and which
    # `upright_bytes` leaves untouched whenever a photograph needed no turning. A landscape
    # photograph would otherwise land on disk with somebody's doorstep in it, beside a row
    # that reads "near Frankfurt".
    data = without_position(data)

    media_type = _MEDIA_TYPES[image_format]
    return StoredPhotograph(
        ref=ImageRef(ref=blobs.put(user_id, data, media_type), media_type=media_type),
        metadata=declared,
    )
