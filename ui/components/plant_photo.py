"""The plant photograph shown on a My Plants card.

Two problems to solve. Uploads are stored under an opaque uuid with the file
extension *not* recorded — ``plants.photo_ref`` holds only the stem — so the file
has to be found by glob rather than constructed. And phone photographs are
usually portrait, so rendering them at their natural aspect would make some cards
twice the height of others; every image is therefore centre-cropped to one fixed
aspect ratio. Equal-width columns then give equal image heights without anyone
choosing a pixel value.
"""

from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

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


def resolve_photo(photo_ref: str | None, upload_dir: Path) -> Path | None:
    """The stored file for a plant's photo reference, or ``None``.

    ``store_upload`` writes ``{ref}.{format}`` but only ``ref`` reaches the
    database, so the extension is recovered by glob. Returns ``None`` for a plant
    with no reference and for one whose file has since been deleted — the uploads
    directory is gitignored scratch, so a missing file is a normal state rather
    than a corruption to shout about.
    """
    if not photo_ref:
        return None
    matches = sorted(upload_dir.glob(f"{photo_ref}.*"))
    return matches[0] if matches else None


@st.cache_data(show_spinner=False)
def _banner_bytes(path: str, mtime: float) -> bytes:
    """Centre-crop an upload to the card aspect ratio, as PNG bytes.

    ``mtime`` is part of the cache key rather than merely informational: keyed on
    the path alone, replacing a file would keep serving the old crop for the life
    of the process.
    """
    with Image.open(path) as opened:
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

    from io import BytesIO

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


def render_plant_photo(photo_ref: str | None, upload_dir: Path) -> None:
    """Render one card's banner, falling back to a placeholder tile.

    Any failure to read or decode the file falls back rather than raising: a
    corrupt upload should cost the owner a thumbnail, not the whole plant grid.
    """
    path = resolve_photo(photo_ref, upload_dir)
    if path is not None:
        try:
            st.image(_banner_bytes(str(path), path.stat().st_mtime), width="stretch")
            return
        except Exception:  # noqa: BLE001 — a bad image must not break the grid
            pass
    st.image(_placeholder_bytes(), width="stretch")
