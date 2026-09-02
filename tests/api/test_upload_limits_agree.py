"""The upload form promises what the server actually accepts.

The form states three limits before somebody picks a file — how many photographs, which
formats, how large — and all three are the server's, copied into the client because an
endpoint for three constants is more machinery than the fact deserves.

Copying is fine. Copying and then drifting is not: the failure is a form that cheerfully
offers something the server refuses, discovered by a person who has already waited for an
upload. Nothing else would notice, which is why this exists.
"""

import pathlib
import re

from core.config import Settings
from core.guards import _MAGIC_BYTES
from tests.secrets import TEST_JWT_SECRET

CLIENT = pathlib.Path("web/src/api/limits.ts")


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET)


def _constant(name: str) -> str:
    source = CLIENT.read_text(encoding="utf-8")
    found = re.search(rf'export const {name} = "?([^";]+)"?;', source)
    assert found is not None, f"{name} is not exported from {CLIENT}"
    return found.group(1).strip()


def test_the_form_offers_as_many_photographs_as_the_server_takes():
    assert int(_constant("MAX_IMAGES")) == _settings().max_images_per_observation


def test_the_form_states_the_size_the_server_enforces():
    assert int(_constant("MAX_IMAGE_MB")) == _settings().max_upload_bytes // (1024 * 1024)


def test_the_picker_offers_exactly_the_formats_the_server_recognises():
    """`accept="image/*"` was the bug this replaces: the server knows PNG and JPEG by their
    magic bytes, so every other image format was offered and then refused after upload."""
    offered = {entry.strip() for entry in _constant("ACCEPTED_TYPES").split(",")}

    assert offered == {f"image/{kind}" for _, kind in _MAGIC_BYTES}
