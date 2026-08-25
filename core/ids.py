"""Record identifiers.

Version 7 rather than 4, and generated here rather than by the database.

**Why v7.** A UUIDv4 is entirely random, so consecutive inserts land in unrelated
places in the primary-key index and each one dirties its own page. A v7 carries a
millisecond timestamp in its leading bits, so identifiers generated in sequence sort in
that sequence and inserts stay local. At this project's size neither is measurable; the
point is that the ordered version costs nothing to choose and stops being free to change
once rows exist.

**Why not the database.** ``gen_random_uuid()`` is v4, and PostgreSQL only grew a native
``uuidv7()`` in 18 — the image here is 17. More decisively, a photograph's blob key and a
plant's identifier are both needed in application code *before* the row is written, and a
value the database assigns on insert is not available until after.

**Why a module for one call.** It is the single place the choice is recorded, so moving
to the standard library's generator (Python 3.14) or to the database later is one edit
rather than a search across every model.
"""

from uuid import UUID

from uuid6 import uuid7


def new_id() -> UUID:
    """Return a fresh time-ordered identifier."""
    return uuid7()
