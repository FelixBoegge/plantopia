"""Multimodal message construction.

The one place image bytes exist in memory. ``ImageRef`` carries a key; this module
resolves it, builds the data URL the model wants, and lets the bytes go. Nothing it
produces is written back into graph state.
"""

import base64
from collections.abc import Sequence

from langchain_core.messages import HumanMessage

from agent.state import ImageRef
from core.blobs import BlobStore


class ImageMissingError(RuntimeError):
    """A referenced photograph is not in the store.

    Raised rather than skipped: a vision call that quietly proceeds on three of four
    photographs produces a diagnosis the owner believes was made from all four.
    """


def build_image_message(
    text: str, images: Sequence[ImageRef], *, blobs: BlobStore, user_id
) -> HumanMessage:
    """Build a human message combining instruction text with one or more images."""
    content: list[dict] = [{"type": "text", "text": text}]
    for image in images:
        data = blobs.get(user_id, image.ref)
        if data is None:
            raise ImageMissingError(f"photograph {image.ref} is not in the store")
        encoded = base64.b64encode(data).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image.media_type};base64,{encoded}"},
            }
        )
    return HumanMessage(content=content)
