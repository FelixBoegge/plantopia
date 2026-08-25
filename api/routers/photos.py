"""Serving a stored photograph.

The one route that talks to a port rather than a service: no service owns image bytes.
Uploads go through ``core.images`` as part of a diagnosis, and a read is a key lookup. It
takes the owner exactly as every other route does — the exception is about layering, not
about scoping.
"""

from uuid import UUID

from fastapi import APIRouter, Response

from api.dependencies import BlobStoreDep, OwnerDep, SessionDep
from data.models import Blob
from data.repositories.errors import RecordNotFoundError

router = APIRouter(prefix="/photos", tags=["photos"])


@router.get("/{key}")
def get_photo(key: UUID, blobs: BlobStoreDep, session: SessionDep, owner: OwnerDep) -> Response:
    """The image bytes, with the content type they were stored under.

    A key belonging to somebody else is indistinguishable from one that matches nothing:
    the store answers ``None`` to both, and this raises the same not-found either way.
    """
    data = blobs.get(owner, key)
    if data is None:
        raise RecordNotFoundError(f"no photograph {key}")

    # The content type lives beside the bytes. Read separately rather than widening the
    # port's return type, because every other caller wants only the bytes.
    stored = session.get(Blob, key)
    return Response(content=data, media_type=stored.content_type)
