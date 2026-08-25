"""The plant photograph shown on a My Plants card.

Photographs come from the blob store, addressed by the key ``plants.photo_ref``
holds. They used to be files on disk found by glob, which stopped working the
moment a container could be replaced between the upload and the page view.

Phone photographs are usually portrait, so rendering them at their natural aspect
would make some cards twice the height of others; every image is therefore
centre-cropped to one fixed aspect ratio. Equal-width columns then give equal
image heights without anyone choosing a pixel value.
"""

from io import BytesIO
from uuid import UUID

import streamlit as st
from PIL import Image, ImageOps

from core.blobs import BlobStore

# 3:4 portrait, because phone photographs of a plant almost always are — every
# upload in testing carried EXIF orientation 6, i.e. 4000x2252 pixels that are
# really 2252x4000. Cropping those to landscape threw away most of the plant.
# Portrait cards are narrower, which is why the grid runs four across.
_ASPECT = 3 / 4
_WIDTH = 600
# #DCE8D9, the sage one shade down from the card surface in .streamlit/config.toml.
# The tile is drawn by Pillow, so it cannot read the theme and has to be kept in
# step by hand; a photoless card should read as an empty surface, not a grey hole.
_PLACEHOLDER_RGB = (220, 232, 217)


def resolve_photo(photo_ref: str | None, blobs: BlobStore, user_id: UUID) -> bytes | None:
    """The stored bytes for a plant's photo reference, or ``None``.

    ``None`` covers a plant with no photograph, a key that no longer resolves, and a key
    belonging to somebody else — the store cannot tell the last two apart on purpose. A
    missing photograph is a normal state here rather than a corruption to shout about:
    the card falls back to a placeholder.
    """
    if not photo_ref:
        return None
    try:
        return blobs.get(user_id, UUID(str(photo_ref)))
    except ValueError:
        # A reference written before photographs moved into the store. Not an error;
        # there is simply nothing behind it any more.
        return None


@st.cache_data(show_spinner=False)
def _banner_bytes(photo_ref: str, data: bytes) -> bytes:
    """Centre-crop an upload to the card aspect ratio, as PNG bytes.

    Keyed on the reference *and* the bytes. The key used to include the file's mtime,
    because keying on a path alone would keep serving the old crop after a file was
    replaced; a blob key is immutable, so the bytes are the honest key and the reference
    is there to keep the cache readable.
    """
    with Image.open(BytesIO(data)) as opened:
        # A phone writes the sensor's raw pixels and records how to turn them in
        # EXIF; Pillow does not apply that on its own. Without this the cards
        # showed every plant lying on its side.
        image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size
        target = width / _ASPECT
        if target <= height:
            top = (height - target) / 2
            box = (0, top, width, top + target)
        else:
            cropped_width = height * _ASPECT
            left = (width - cropped_width) / 2
            box = (left, 0, left + cropped_width, height)
        banner = image.crop(tuple(round(v) for v in box)).resize((_WIDTH, round(_WIDTH / _ASPECT)))

    buffer = BytesIO()
    banner.save(buffer, format="PNG")
    return buffer.getvalue()


@st.cache_data(show_spinner=False)
def _placeholder_bytes() -> bytes:
    """A plain tile at the card aspect ratio, for a plant with no usable photo.

    Deliberately an image rather than an empty gap: a card without one would be
    shorter than its neighbours, which is the unevenness the fixed aspect exists
    to remove.
    """
    from io import BytesIO

    tile = Image.new("RGB", (_WIDTH, round(_WIDTH / _ASPECT)), _PLACEHOLDER_RGB)
    buffer = BytesIO()
    tile.save(buffer, format="PNG")
    return buffer.getvalue()


def render_plant_photo(photo_ref: str | None, blobs: BlobStore, user_id: UUID) -> None:
    """Render one card's banner, falling back to a placeholder tile.

    Any failure to read or decode the photograph falls back rather than raising: a
    corrupt upload should cost the owner a thumbnail, not the whole plant grid.
    """
    data = resolve_photo(photo_ref, blobs, user_id)
    if data is not None:
        try:
            st.image(_banner_bytes(str(photo_ref), data), width="stretch")
            return
        except Exception:  # noqa: BLE001 — a bad image must not break the grid
            pass
    st.image(_placeholder_bytes(), width="stretch")
