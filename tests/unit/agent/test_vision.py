"""Tests for multimodal message construction.

The bytes live in the blob store now, so these use a fake one: what matters here is
that a key becomes a data URL, and that a key with nothing behind it is refused rather
than skipped.
"""

import base64

import pytest
from langchain_core.messages import HumanMessage

from agent.state import ImageRef
from agent.vision import ImageMissingError, build_image_message
from core.ids import new_id

OWNER = new_id()
PIXELS = b"hello"
ENCODED = base64.b64encode(PIXELS).decode("ascii")


class FakeBlobs:
    """A blob store in a dict. Owner-scoped, like the real one."""

    def __init__(self) -> None:
        self._data: dict[tuple, bytes] = {}

    def put(self, user_id, data: bytes, content_type: str):
        key = new_id()
        self._data[(user_id, key)] = data
        return key

    def get(self, user_id, key):
        return self._data.get((user_id, key))

    def delete_for_user(self, user_id) -> int:
        keys = [k for k in self._data if k[0] == user_id]
        for k in keys:
            del self._data[k]
        return len(keys)


@pytest.fixture
def blobs():
    return FakeBlobs()


def _image(blobs, media_type: str = "image/png", data: bytes = PIXELS) -> ImageRef:
    return ImageRef(ref=blobs.put(OWNER, data, media_type), media_type=media_type)


def _message(blobs, text: str, images):
    return build_image_message(text, images, blobs=blobs, user_id=OWNER)


def test_returns_a_human_message(blobs):
    assert isinstance(_message(blobs, "look", [_image(blobs)]), HumanMessage)


def test_text_is_the_first_content_block(blobs):
    message = _message(blobs, "What is wrong?", [_image(blobs)])
    assert message.content[0] == {"type": "text", "text": "What is wrong?"}


def test_every_image_becomes_a_content_block(blobs):
    images = [_image(blobs), _image(blobs), _image(blobs)]
    message = _message(blobs, "look", images)
    assert len([b for b in message.content if b["type"] == "image_url"]) == 3


def test_images_are_encoded_as_data_urls(blobs):
    message = _message(blobs, "look", [_image(blobs)])
    assert message.content[1]["image_url"]["url"] == f"data:image/png;base64,{ENCODED}"


def test_media_type_is_carried_through(blobs):
    message = _message(blobs, "look", [_image(blobs, media_type="image/jpeg")])
    assert message.content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_works_with_no_images(blobs):
    assert len(_message(blobs, "text only", []).content) == 1


def test_a_missing_photograph_raises_rather_than_being_skipped(blobs):
    """A vision call that quietly proceeds on three of four photographs produces a
    diagnosis the owner believes was made from all four."""
    present = _image(blobs)
    absent = ImageRef(ref=new_id(), media_type="image/png")

    with pytest.raises(ImageMissingError):
        _message(blobs, "look", [present, absent])


def test_another_owners_photograph_is_missing(blobs):
    """The store is owner-scoped, so a key from elsewhere resolves to nothing — and
    that has to fail loudly rather than silently drop the image."""
    image = _image(blobs)

    with pytest.raises(ImageMissingError):
        build_image_message("look", [image], blobs=blobs, user_id=new_id())
