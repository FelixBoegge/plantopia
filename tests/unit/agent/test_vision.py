"""Tests for multimodal message construction."""

from langchain_core.messages import HumanMessage

from agent.state import ImageRef
from agent.vision import build_image_message


def _image(ref: str = "img-1") -> ImageRef:
    return ImageRef(ref=ref, media_type="image/png", data_b64="aGVsbG8=")


def test_returns_a_human_message():
    assert isinstance(build_image_message("look", [_image()]), HumanMessage)


def test_text_is_the_first_content_block():
    message = build_image_message("What is wrong?", [_image()])
    assert message.content[0] == {"type": "text", "text": "What is wrong?"}


def test_every_image_becomes_a_content_block():
    message = build_image_message("look", [_image("a"), _image("b"), _image("c")])
    image_blocks = [b for b in message.content if b["type"] == "image_url"]
    assert len(image_blocks) == 3


def test_images_are_encoded_as_data_urls():
    message = build_image_message("look", [_image()])
    url = message.content[1]["image_url"]["url"]
    assert url == "data:image/png;base64,aGVsbG8="


def test_media_type_is_carried_through():
    image = ImageRef(ref="x", media_type="image/jpeg", data_b64="Zm9v")
    message = build_image_message("look", [image])
    assert message.content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_works_with_no_images():
    message = build_image_message("text only", [])
    assert len(message.content) == 1
