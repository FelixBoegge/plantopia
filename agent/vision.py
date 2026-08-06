"""Multimodal message construction."""

from collections.abc import Sequence

from langchain_core.messages import HumanMessage

from agent.state import ImageRef


def build_image_message(text: str, images: Sequence[ImageRef]) -> HumanMessage:
    """Build a human message combining instruction text with one or more images."""
    content: list[dict] = [{"type": "text", "text": text}]
    content.extend(
        {
            "type": "image_url",
            "image_url": {"url": f"data:{image.media_type};base64,{image.data_b64}"},
        }
        for image in images
    )
    return HumanMessage(content=content)
