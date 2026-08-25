"""Persistence for treatment-outcome feedback."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import Diagnosis, Feedback, Plant
from data.repositories._ownership import require_diagnosis

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

    Write methods do not commit; the caller groups writes with ``data.engine.transaction``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """The underlying session, for callers that need to group writes."""
        return self._session

    def create(
        self,
        user_id: UUID,
        *,
        diagnosis_id: UUID,
        rating: int | None,
        did_it_help: DidItHelp | None,
        free_text: str | None,
        now: datetime,
    ) -> UUID:
        require_diagnosis(self._session, user_id, diagnosis_id)
        row = Feedback(
            diagnosis_id=diagnosis_id,
            rating=rating,
            did_it_help=did_it_help,
            free_text=free_text,
            created_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def exists_for_diagnosis(self, user_id: UUID, diagnosis_id: UUID) -> bool:
        """Whether feedback has already been recorded for this diagnosis.

        The Plant detail page uses this to avoid re-prompting for feedback already
        given. Another owner's diagnosis answers ``False`` — the same answer an
        unknown diagnosis gives, so the question cannot be used to discover one.
        """
        found = self._session.scalar(
            select(Feedback.id)
            .join(Diagnosis, Feedback.diagnosis_id == Diagnosis.id)
            .join(Plant, Diagnosis.plant_id == Plant.id)
            .where(Feedback.diagnosis_id == diagnosis_id, Plant.user_id == user_id)
            .limit(1)
        )
        return found is not None
