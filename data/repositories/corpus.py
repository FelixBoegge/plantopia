"""Reading the disorder corpus by identifier.

**The one repository that takes no ``user_id``.** Every other one takes it as a required
first parameter and enforces tenancy there rather than trusting a caller — but the corpus
has no owner. ``data/models.CorpusChunk`` states the reason: it is reference data,
identical for everybody and unchanged by anything anybody does, so there is no tenancy
question to answer and a ``user_id`` here would be a parameter that lies about what it
protects.

Retrieval itself does not come through here — that is ``knowledge/pgvector_retriever.py``,
which searches by vector. This is for callers holding identifiers they got from somewhere
else, and today there is one: a stored diagnosis lists the passages it consulted as
``(doc_id, section)`` pairs, and a screen showing them needs the name a reader would
recognise.
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import CorpusChunk


class CorpusRepository:
    """The corpus, by identifier rather than by similarity."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def names_for(self, doc_ids: Sequence[str]) -> dict[str, str]:
        """The display name of each named document, keyed by ``doc_id``.

        **A document absent from the corpus is absent from the result**, rather than
        present with a blank or raising. An old diagnosis can cite a disorder since renamed
        or removed, and a caller has to be able to tell "no name recorded" from "the name is
        empty" in order to decide what to show — so the distinction is preserved here rather
        than flattened into a string nobody can act on.

        Deliberately not derived from the slug by the caller. Three of the 43 documents
        disagree with their own id — ``botrytis`` is "Botrytis (grey mould)", ``pot-bound``
        is "Pot-bound (root-bound)", ``damping-off`` keeps a hyphen a naive
        title-casing drops — so a name computed from the id would be wrong on the documents
        whose names carry the most information.

        Returns immediately for an empty request: a diagnosis that retrieved nothing must
        not turn into a query that reads the whole table.
        """
        if not doc_ids:
            return {}

        rows = self._session.execute(
            select(CorpusChunk.doc_id, CorpusChunk.name)
            .where(CorpusChunk.doc_id.in_(set(doc_ids)))
            .distinct()
        ).all()
        return {doc_id: name for doc_id, name in rows}
