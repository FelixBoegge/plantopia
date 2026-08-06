"""Upload handling: validate, store outside the served path, return a reference."""

import base64
import uuid
from pathlib import Path

from agent.state import ImageRef
from core.config import Settings
from core.guards import validate_upload

_MEDIA_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def store_upload(data: bytes, upload_dir: Path, settings: Settings) -> ImageRef:
    """Validate an upload, persist it under an opaque id, and return a reference.

    Raises:
        UploadRejected: if validation fails.
    """
    image_format = validate_upload(data, settings)

    upload_dir.mkdir(parents=True, exist_ok=True)
    ref = uuid.uuid4().hex
    (upload_dir / f"{ref}.{image_format}").write_bytes(data)

    return ImageRef(
        ref=ref,
        media_type=_MEDIA_TYPES[image_format],
        data_b64=base64.b64encode(data).decode("ascii"),
    )
