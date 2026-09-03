"""Turn the generated logo into the assets the web client uses.

Run from the repository root:

    uv run python design/extract_logo_assets.py

Reads `design/plantopia-logo-source.png` and writes three files into `web/public/`. The
source is a 2048px square: a white mark over a green gradient, with the "Plantopia"
wordmark beneath it.

**Why the background is keyed on `g - b` and not on brightness.** The gradient runs from
saturated green in one corner to *near-white* in the opposite one, and that pale corner is
as bright as the mark itself — a brightness threshold keeps half the background. What does
separate them is neutrality: the mark measures about +7 on `g - b` while every part of the
gradient sits at +14 or higher. The margin is narrow, hence the two clean-up passes below.

**Why the mark ships as a mask rather than a picture.** Cut the background out and the mark
is white, which is invisible against the light theme's sage. Keep the background and every
placement carries a green tile. So `logo-mark.png` is used for its alpha alone and takes its
colour from the page — see `.logo-mark` in `web/src/styles/index.css`.

**Why the tab icon keeps its background.** A favicon is a filled tile on somebody else's
colour. The silhouette would vanish against a pale tab strip, so that one asset stays as
drawn.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "design" / "plantopia-logo-source.png"
PUBLIC = ROOT / "web" / "public"

# Where the wordmark starts. Everything above this row is the mark, and the two are
# separated by a clear horizontal band of background in the source. Replacing the artwork
# means finding this row again: the widest all-background gap in
# `np.flatnonzero((alpha > 0.5).any(axis=1))` is it.
WORDMARK_TOP = 1285

# The first row of the lettering itself. Between this and `WORDMARK_TOP` is empty
# background, and the square above is allowed to reach into it but no further.
WORDMARK_LETTERS = 1353

# Below +8 on `g - b` a pixel is the mark; above +22 it is background; between the two it is
# an edge, and the ramp is what keeps those edges smooth rather than jagged.
NEUTRAL = 8.0
GREEN = 22.0


def silhouette(rgb: np.ndarray) -> np.ndarray:
    """Alpha for the mark: 1 on the artwork, 0 on the gradient, soft in between."""
    g, b = rgb[..., 1], rgb[..., 2]
    luminance = rgb.mean(axis=2)

    alpha = np.clip((GREEN - (g - b)) / (GREEN - NEUTRAL), 0, 1)
    alpha *= np.clip((luminance - 120.0) / 60.0, 0, 1)

    # The mark touches no edge of the canvas, so anything that reaches one is background.
    # This is what removes the pale corner, which is neutral enough to pass the test above.
    height, width = alpha.shape
    reachable = Image.new("L", (width + 2, height + 2), 255)
    reachable.paste(Image.fromarray(((alpha > 0.35) * 255).astype(np.uint8)), (1, 1))
    ImageDraw.floodfill(reachable, (0, 0), 128, thresh=0)
    alpha[np.asarray(reachable)[1:-1, 1:-1] == 128] = 0

    # The pale corner is grainy, and grain that is not border-connected survives as speckle.
    # An opening deletes anything thinner than the kernel, which removes most of it.
    binary = Image.fromarray(((alpha > 0.35) * 255).astype(np.uint8), "L")
    opened = binary.filter(ImageFilter.MinFilter(9)).filter(ImageFilter.MaxFilter(9))
    alpha = alpha * (np.asarray(opened.filter(ImageFilter.MaxFilter(5))) > 127)

    # Most, not all: a speck thicker than the kernel outlives it, and one did — a dot of
    # noise floating above the mark, which is visible on screen and quietly widens the crop
    # around the artwork. Thickness is the wrong test for it; size is the right one. The
    # wordmark's smallest piece is the dot on the "i", so the floor sits well below that.
    return _drop_specks(alpha, min_area=alpha.size // 4000)


def _drop_specks(alpha: np.ndarray, min_area: int) -> np.ndarray:
    """Zero every run of ink smaller than `min_area` pixels."""
    canvas = Image.fromarray(((alpha > 0.35) * 255).astype(np.uint8), "L")
    pixels = np.asarray(canvas)

    kept = np.zeros_like(pixels, dtype=bool)
    while True:
        remaining = np.argwhere(np.asarray(canvas) == 255)
        if not len(remaining):
            break
        y, x = remaining[0]
        ImageDraw.floodfill(canvas, (int(x), int(y)), 64, thresh=0)
        blob = np.asarray(canvas) == 64
        if blob.sum() >= min_area:
            kept |= blob
        # Mark it seen either way, so the next pass finds a different blob.
        canvas.paste(Image.new("L", canvas.size, 128), (0, 0), Image.fromarray(blob))

    return alpha * kept


def mark_bounds(alpha: np.ndarray) -> tuple[int, ...]:
    """Exactly the mark, no margin: everything with ink in it above the wordmark."""
    above = alpha[:WORDMARK_TOP]
    rows = np.flatnonzero((above > 0.5).any(axis=1))
    cols = np.flatnonzero((above > 0.5).any(axis=0))
    return (cols[0], rows[0], cols[-1] + 1, rows[-1] + 1)


def centred_square(mask: Image.Image, pad_fraction: float = 0.04) -> Image.Image:
    """The mask centred on a transparent square, with an equal margin on every side.

    Built rather than cropped. Cutting a square out of the source meant the square's size
    was driven by the mark's wider dimension, which pushed its bottom edge down into the
    wordmark — and clamping that edge is what left the mark flush against the bottom of its
    own frame, reading as low beside any text it sat next to. Pasting onto a canvas makes
    the centring exact and independent of what happens to be nearby in the artwork.
    """
    side = round(max(mask.width, mask.height) * (1 + 2 * pad_fraction))
    square = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    square.paste(mask, ((side - mask.width) // 2, (side - mask.height) // 2))
    return square


def _mask(alpha: np.ndarray, box: tuple[int, ...]) -> Image.Image:
    """The alpha inside `box` as an image, white throughout: a mask reads nothing else."""
    cut = alpha[box[1] : box[3], box[0] : box[2]]
    shape = np.zeros((*cut.shape, 4), dtype=np.uint8)
    shape[..., :3] = 255
    shape[..., 3] = (cut * 255).astype(np.uint8)
    return Image.fromarray(shape, "RGBA")


def _bounds(alpha: np.ndarray, width: int, height: int, pad: int = 20) -> tuple[int, ...]:
    """Everything with ink in it, plus an equal margin."""
    rows = np.flatnonzero((alpha > 0.5).any(axis=1))
    cols = np.flatnonzero((alpha > 0.5).any(axis=0))
    return (
        max(0, cols[0] - pad),
        max(0, rows[0] - pad),
        min(width, cols[-1] + pad),
        min(height, rows[-1] + pad),
    )


def main() -> None:
    image = Image.open(SOURCE).convert("RGB")
    rgb = np.asarray(image).astype(np.float32)
    alpha = silhouette(rgb)
    box = mark_bounds(alpha)

    PUBLIC.mkdir(parents=True, exist_ok=True)

    centred_square(_mask(alpha, box)).resize((512, 512), Image.LANCZOS).save(
        PUBLIC / "logo-mark.png"
    )

    # The whole lockup — mark and wordmark together — for the screens that have room for
    # it. Not square: cropped to its own bounds with an equal margin, so the proportions
    # come from the artwork rather than from a frame chosen here.
    lockup = _mask(alpha, _bounds(alpha, image.width, image.height))
    lockup.resize((640, round(640 * lockup.height / lockup.width)), Image.LANCZOS).save(
        PUBLIC / "logo-lockup.png"
    )

    # 128px, not 512: a tab icon is drawn at 16-32 CSS pixels, and 512 of a gradient was a
    # third of a megabyte for a thumbnail nobody ever sees full size.
    # The tile is a crop of the artwork itself, so unlike the masks it cannot be built on a
    # canvas — it needs real pixels behind the mark. Squared around the mark and held above
    # the lettering, which costs a few pixels of symmetry nobody can see at 32px.
    side = max(box[2] - box[0], box[3] - box[1])
    centre_x, centre_y = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    half = min(side // 2 + 24, WORDMARK_LETTERS - centre_y - 1)
    tile = image.crop((centre_x - half, centre_y - half, centre_x + half, centre_y + half))
    tile.resize((128, 128), Image.LANCZOS).save(PUBLIC / "favicon.png", optimize=True)
    tile.resize((180, 180), Image.LANCZOS).save(PUBLIC / "apple-touch-icon.png", optimize=True)

    for name in ("logo-mark.png", "logo-lockup.png", "favicon.png", "apple-touch-icon.png"):
        written = PUBLIC / name
        print(f"  {name:22} {written.stat().st_size / 1024:6.1f} kB")

    # A mask has no intrinsic size, so `.logo-lockup` in the stylesheet carries this ratio
    # by hand. Printed here because the two drift silently otherwise: the mask would simply
    # letterbox itself inside a box of the wrong shape.
    made = Image.open(PUBLIC / "logo-lockup.png")
    print()
    print(f"  .logo-lockup in index.css needs: aspect-ratio: {made.width} / {made.height};")


if __name__ == "__main__":
    main()
