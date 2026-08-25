"""Where uploaded photographs live.

A port with one adapter. The port exists now and the S3 adapter does not, which is
deliberate: the shape of the interface is what has to be right today, because it is
what every caller is written against.

**Keys are opaque.** Callers never build one, never parse one, and never assume it
encodes a location, a filename, an order or a count. That is the whole property that
lets the bytes move to object storage later without touching a single caller.

**Bytes never enter graph state.** ``ImageRef`` carries a key; the one place that needs
the actual image — the vision call — loads it here. ``M15`` measured what the other
arrangement costs: two diagnoses of 3 MB photographs produced 205 MB of checkpoint
blobs, because LangGraph re-serialises the whole state at every superstep and the state
held base64.
"""

from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.ids import new_id
from data.models import Blob


class BlobStore(Protocol):
    """Storage for uploaded photographs, addressed by opaque key."""

    def put(self, user_id: UUID, data: bytes, content_type: str) -> UUID:
        """Store bytes for an owner and return the key that retrieves them."""
        ...

    def get(self, user_id: UUID, key: UUID) -> bytes | None:
        """The bytes, or ``None`` if the key is unknown *or* not this owner's.

        The two are deliberately indistinguishable: an answer that separated them
        would confirm that somebody else's photograph exists.
        """
        ...

    def delete_for_user(self, user_id: UUID) -> int:
        """Remove every photograph belonging to one owner. Returns how many went."""
        ...


class PostgresBlobStore:
    """Bytes in a ``bytea`` column, in the same database as everything else.

    One datastore, one backup, one transaction — a photograph and the observation that
    references it are written or lost together, which an object store could not promise.
    The cost is that multi-megabyte reads travel through the same connection pool the
    rest of the application uses; at one image per vision call that is not yet a
    problem, and the port is how it stops being this class's problem when it is.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def put(self, user_id: UUID, data: bytes, content_type: str) -> UUID:
        # The key is assigned here rather than left to the column default: it *is* the
        # return value, so it has to exist before the flush rather than after it.
        key = new_id()
        self._session.add(
            Blob(
                id=key,
                user_id=user_id,
                content_type=content_type,
                byte_size=len(data),
                data=data,
            )
        )
        self._session.flush()
        return key

    def get(self, user_id: UUID, key: UUID) -> bytes | None:
        return self._session.scalar(
            select(Blob.data).where(Blob.id == key, Blob.user_id == user_id)
        )

    def delete_for_user(self, user_id: UUID) -> int:
        rows = self._session.scalars(select(Blob).where(Blob.user_id == user_id)).all()
        for row in rows:
            self._session.delete(row)
        return len(rows)
