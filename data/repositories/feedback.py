"""Persistence for treatment-outcome feedback."""

import sqlite3
from datetime import datetime
from typing import Literal

DidItHelp = Literal["yes", "no", "unclear", "too_early"]


# No ``FeedbackRecord`` dataclass and no ``_to_record`` row mapper here, unlike every
# other repository in this package: nothing reads a feedback row back into the app. The
# Plant detail page only needs to know *whether* feedback exists
# (``exists_for_diagnosis``), and the answers themselves are for the owner to query
# offline. Both were written speculatively in Phase 2 and never called, so they are gone
# rather than left as working code nothing exercises — add them back together with the
# read method that needs them.
class FeedbackRepository:
    """Reads and writes the ``feedback`` table.

    Write methods do not commit; the caller groups writes with ``data.db.transaction``.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, for callers that need to group writes."""
        return self._conn

    def create(
        self,
        *,
        diagnosis_id: int,
        rating: int | None,
        did_it_help: DidItHelp | None,
        free_text: str | None,
        now: datetime,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO feedback (diagnosis_id, rating, did_it_help, free_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (diagnosis_id, rating, did_it_help, free_text, now.isoformat()),
        )
        return int(cursor.lastrowid)

    def exists_for_diagnosis(self, diagnosis_id: int) -> bool:
        """Whether feedback has already been recorded for this diagnosis.

        The Plant detail page uses this to avoid re-prompting for feedback already
        given.
        """
        row = self._conn.execute(
            "SELECT 1 FROM feedback WHERE diagnosis_id = ? LIMIT 1", (diagnosis_id,)
        ).fetchone()
        return row is not None
