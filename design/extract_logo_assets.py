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
    # An opening deletes anything thinner than the kernel; the mark's thinnest part, the
    # stem, is far thicker.
    binary = Image.fromarray(((alpha > 0.35) * 255).astype(np.uint8), "L")
    opened = binary.filter(ImageFilter.MinFilter(9)).filter(ImageFilter.MaxFilter(9))
    return alpha * (np.asarray(opened.filter(ImageFilter.MaxFilter(5))) > 127)


def square_around_the_mark(alpha: np.ndarray, width: int, pad: int = 24) -> tuple[int, ...]:
    """The smallest square holding the mark, so it keeps its proportions at any size."""
    above = alpha[:WORDMARK_TOP]
    rows = np.flatnonzero((above > 0.5).any(axis=1))
    cols = np.flatnonzero((above > 0.5).any(axis=0))
    top, bottom = max(0, rows[0] - pad), min(WORDMARK_TOP, rows[-1] + pad)
    left, right = max(0, cols[0] - pad), min(width, cols[-1] + pad)

    half = max(bottom - top, right - left) // 2
    centre_y, centre_x = (top + bottom) // 2, (left + right) // 2
    return (centre_x - half, centre_y - half, centre_x + half, centre_y + half)


def main() -> None:
    image = Image.open(SOURCE).convert("RGB")
    rgb = np.asarray(image).astype(np.float32)
    alpha = silhouette(rgb)
    box = square_around_the_mark(alpha, image.width)

    PUBLIC.mkdir(parents=True, exist_ok=True)

    mark = alpha[box[1] : box[3], box[0] : box[2]]
    shape = np.zeros((*mark.shape, 4), dtype=np.uint8)
    shape[..., :3] = 255  # White, because a mask reads nothing but the alpha.
    shape[..., 3] = (mark * 255).astype(np.uint8)
    Image.fromarray(shape, "RGBA").resize((512, 512), Image.LANCZOS).save(PUBLIC / "logo-mark.png")

    # 128px, not 512: a tab icon is drawn at 16-32 CSS pixels, and 512 of a gradient was a
    # third of a megabyte for a thumbnail nobody ever sees full size.
    tile = image.crop(box)
    tile.resize((128, 128), Image.LANCZOS).save(PUBLIC / "favicon.png", optimize=True)
    tile.resize((180, 180), Image.LANCZOS).save(PUBLIC / "apple-touch-icon.png", optimize=True)

    for name in ("logo-mark.png", "favicon.png", "apple-touch-icon.png"):
        written = PUBLIC / name
        print(f"  {name:22} {written.stat().st_size / 1024:6.1f} kB")


if __name__ == "__main__":
    main()
