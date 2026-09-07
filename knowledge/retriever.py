"""What the diagnosis graph needs from a retriever.

The Protocol only. The implementation is ``knowledge/pgvector_retriever.py``; this exists
so the nodes depend on the shape rather than on the store, which is what let the store
change underneath them without a rewrite.

Three members, and it used to be five. ``supports_image_search`` and ``search_by_image``
described the cross-modal path — embedding a photograph into the corpus's own vector space
— which was removed with Chroma because no reachable embedding model can supply it
(``U2``). A Protocol member nothing can implement honestly is not an extension point.
"""

from collections.abc import Sequence
from typing import Protocol

from agent.schemas import Passage


class Retriever(Protocol):
    """What the enrich node needs from retrieval."""

    def search(
        self, queries: Sequence[str], k: int, *, sections: Sequence[str] | None = None
    ) -> list[Passage]:
        """Return the best ``k`` passages across every query, best first.

        At most one passage per disorder, so ``k`` slots describe ``k`` candidates.
        ``sections`` restricts which sections may match at all; ``None`` allows any.
        """
        ...

    def sections_for(self, doc_ids: Sequence[str], sections: Sequence[str]) -> list[Passage]:
        """Fetch named sections of named documents directly, by id rather than by score.

        For material a caller knows it wants once a document is in contention, which
        similarity search will not reliably surface on its own — see
        ``tools.knowledge.search_plant_knowledge``.
        """
        ...

    def known_doc_ids(self) -> tuple[str, ...]:
        """Every disorder in the corpus, sorted.

        Offered so a caller can ask a model to *name* disorders and then look them up,
        rather than only finding them by similarity — see ``agent/nodes/hypothesise.py``.
        """
        ...
